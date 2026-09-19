"""Per-task orchestration: advisory whole-task planning and exact Jev choices."""

import json
import threading
import time
from copy import deepcopy
from urllib.parse import urlsplit

from ctrl.browser_scope import host_allowed
from ctrl.credentials import CredentialError
from jev_ultrafast import model as jev_model
from jev_ultrafast.browser import ActionPaused
from jev_ultrafast.navigation import navigation_urls

from .grounding import NONE, FiniteTargets, GroundingError
from .planner import MAX_REQUEST_BYTES, PlannerClient, PlannerError, validate_plan

MAX_PLANNER_CALLS = 64
REFRESH_ACTIONS = 4
TERMINALS = {"DONE", "BLOCKED", "NEEDS_INPUT", NONE}


def page_location(page):
    """Refresh site-level intent across origins, without replanning every path."""
    try:
        address = urlsplit(page.get("url", ""))
        port = address.port or {"https": 443, "http": 80}.get(address.scheme)
    except ValueError:
        raise PlannerError("Observed page has an invalid address; no action executed.") from None
    return bool(page.get("bootstrap")), address.scheme, address.hostname, port


def page_observation(page):
    """Terminal evidence belongs only to the exact observed page that produced it."""
    return tuple(page.get(name) for name in ("observation_id", "fingerprint", "url", "target_id"))


class HybridDecider:
    def __init__(self, *, model=None, cancel_event=None, planner=None, jev_choose=None):
        self.planner = planner or PlannerClient(model)
        self.cancel_event = cancel_event
        self.jev_choose = jev_choose or jev_model.choose
        self._lock = threading.RLock()
        self._choosing = threading.Lock()
        self._goal = None
        self._values = None
        self._current = None
        self._trace = []
        self._last_plan_actions = 0
        self._last_plan_location = None
        self._last_plan_observation = None
        self._largest_history = 0
        self._force_refresh = False
        self._failure = None

    def snapshot(self):
        with self._lock:
            return deepcopy({
                "model": self.planner.model, "call_count": len(self._trace), "max_calls": MAX_PLANNER_CALLS,
                "current": self._current, "trace": self._trace,
            })

    def _check_cancel(self):
        if self.cancel_event is not None and self.cancel_event.is_set():
            self._force_refresh = True
            raise ActionPaused("Paused before the next hybrid decision.")

    def _plan(self, page, goal, history, values, reason, terminal=None):
        self._check_cancel()
        if len(self._trace) >= MAX_PLANNER_CALLS:
            raise PlannerError("Reached the 64-call planner limit; no action executed.")
        scope = jev_model.task_browser_scope(page)
        actions = jev_model.scoped_actions(page, scope)
        recent, prior = jev_model.history_context(history, scope)
        outside = scope and scope["outside_scope"]
        context = {
            "original_goal": goal, "task_browser_scope": scope,
            "page": {"url": "" if outside else page["url"], "title": "" if outside else page["title"][:240],
                     "text": "" if outside else page["text"][:6000]},
            "offered_actions": FiniteTargets(actions).descriptions(),
            "supplied_values": {f"v{index}": value for index, value in enumerate(values, 1)},
            "recent_actions": recent, "prior_progress": prior,
            "previous_public_plan": self._current,
            "refresh_reason": reason,
            "jev_terminal": None if terminal is None else {
                "operation": terminal["operation"],
                "stop_reason": terminal.get("stop_reason")
                if terminal.get("stop_reason") in {*jev_model.BLOCKED_REASONS, *jev_model.INPUT_REASONS} else None,
            },
        }
        body = self.planner.request_body(context)
        request_bytes = len(json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode())
        if request_bytes > MAX_REQUEST_BYTES:
            raise PlannerError("Planner context is too large; narrow the task or supplied values.")
        entry = {
            "sequence": len(self._trace) + 1, "model": self.planner.model, "reason": reason,
            "action_count": len(history), "status": "pending", "request_bytes": request_bytes, "latency_ms": None,
            "jev_terminal": terminal["operation"] if terminal else None,
        }
        with self._lock:
            self._trace.append(entry)
        started = time.perf_counter()
        try:
            plan = validate_plan(self.planner.complete(body, self._check_cancel))
            self._check_cancel()
            if plan["status"] == "done" and (outside or page.get("bootstrap") or page.get("scope_blocked")):
                raise PlannerError("Planner claimed completion before a task page was observed; no action executed.")
            if scope:
                for destination in navigation_urls(plan["next_subgoal"]):
                    if not host_allowed(destination, scope["allowed_hosts"]):
                        raise PlannerError("Planner attempted to change task destinations; no action executed.")
            with self._lock:
                self._current = plan
                self._last_plan_actions = len(history)
                self._last_plan_location = page_location(page)
                self._last_plan_observation = page_observation(page)
                self._values = values
                self._force_refresh = False
                entry.update(plan)
        except ActionPaused:
            with self._lock:
                entry["status"] = "cancelled"
            raise
        except (PlannerError, CredentialError):
            with self._lock:
                entry["status"] = "error"
                self._current = None
            raise
        finally:
            with self._lock:
                entry["latency_ms"] = round((time.perf_counter() - started) * 1000)
        return plan

    def _terminal(self, operation, reason=None):
        entry = self._trace[-1] if self._trace else {}
        return {
            "choice": operation, "operation": operation, "target": None, "payload_id": None, "text": None,
            "stop_reason": reason, "confidence": None, "probabilities": {}, "operation_probabilities": {},
            "target_probabilities": {}, "target_confidence": None, "model": self.planner.model, "usage": {},
            "latency_ms": entry.get("latency_ms", 0), "request_bytes": entry.get("request_bytes", 0),
            "decision_source": "planner", "audit": {
                "questions": [], "selected": {"operation": operation, "action_id": None, "target_id": None,
                                                "target_label": self._current.get("completion_evidence", "")
                                                if self._current else ""},
                "model": self.planner.model, "latency_ms": entry.get("latency_ms", 0),
                "request_bytes": entry.get("request_bytes", 0),
            },
        }

    def choose(self, page, original_goal, history, values=None):
        if not self._choosing.acquire(blocking=False):
            raise PlannerError("A hybrid decision is already in progress.")
        try:
            return self._choose(page, original_goal, history, values)
        except PlannerError as error:
            self._failure = str(error)
            raise
        finally:
            self._choosing.release()

    def _choose(self, page, original_goal, history, values):
        self._check_cancel()
        if self._failure:
            raise PlannerError(self._failure)
        if not isinstance(original_goal, str) or not original_goal.strip() or len(original_goal) > 8000:
            raise PlannerError("Enter a task of 1–8,000 characters.")
        if self._goal is not None and self._goal != original_goal:
            raise PlannerError("Create a new hybrid decider when starting a different task.")
        if not isinstance(history, list) or len(history) < self._largest_history:
            raise PlannerError("Create a new hybrid decider when resetting task history.")
        self._goal = original_goal
        self._largest_history = len(history)
        exact_values = jev_model.supplied_values(original_goal, values)
        scope = jev_model.task_browser_scope(page)
        offered = FiniteTargets(jev_model.scoped_actions(page, scope))
        refresh = None
        if self._current is None:
            refresh = "first_step"
        elif self._force_refresh or self._values != exact_values:
            refresh = "context_changed"
        elif self._current["status"] != "continue" and self._last_plan_observation != page_observation(page):
            refresh = "terminal_observation_changed"
        elif self._last_plan_location != page_location(page):
            refresh = "page_context_changed"
        elif len(history) - self._last_plan_actions >= REFRESH_ACTIONS:
            refresh = "action_interval"
        elif len(history) > self._last_plan_actions and history[-1].get("page_changed") is False:
            refresh = "no_progress"
        if refresh:
            self._plan(page, original_goal, history, exact_values, refresh)
        for attempt in range(2):
            self._check_cancel()
            if self._current["status"] != "continue":
                return self._terminal("DONE") if self._current["status"] == "done" else (
                    self._terminal("BLOCKED", "cannot_progress")
                )
            context_page = {**page, "planner_context": {
                name: self._current[name] for name in ("next_subgoal", "progress_summary", "completion_evidence")
            }}
            decision = self.jev_choose(context_page, original_goal, history, exact_values)
            self._check_cancel()
            operation = decision.get("operation")
            none_selected = decision.get("choice") == NONE and offered.resolve(decision["choice"]) is None
            if operation not in TERMINALS and not none_selected:
                observed = offered.resolve(decision.get("choice"))
                _, targets, controls = jev_model.decision_space(list(offered.actions.values()), exact_values)
                candidate = targets.get(operation, {}).get(decision.get("target")) or controls.get(operation)
                if candidate is None or candidate["id"] != observed["id"]:
                    raise GroundingError("Jev did not select a matching offered operation and target.")
                if operation == "TYPE_TEXT" and (
                    candidate.get("payload_id") != decision.get("payload_id")
                    or candidate["text"] != decision.get("text")
                ):
                    raise GroundingError("Jev selected text outside the exact supplied values.")
                return decision
            if not none_selected and (operation not in TERMINALS or decision.get("choice") != operation):
                raise GroundingError("Jev returned an inconsistent terminal selection.")
            report = {**decision, "operation": NONE} if none_selected else decision
            plan = self._plan(page, original_goal, history, exact_values, "jev_terminal", terminal=report)
            if none_selected:
                # Explicit none never falls through to another candidate, even after replanning.
                return self._terminal("BLOCKED", "unavailable_control")
            if operation in {"BLOCKED", "NEEDS_INPUT"}:
                return decision
            if plan["status"] != "continue":
                return self._terminal("DONE") if plan["status"] == "done" else (
                    self._terminal("BLOCKED", "cannot_progress")
                )
            if attempt == 1:
                raise PlannerError("Jev could not ground the remaining task after replanning; no action executed.")
        raise PlannerError("Hybrid decision ended without an executable selection.")
