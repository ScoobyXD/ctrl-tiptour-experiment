"""Hybrid planning contracts: synthetic responses only, no browser or credentials."""

import json
from threading import Event
from unittest.mock import Mock

import httpx
import pytest

from hybrid import DEFAULT_MODEL, HybridDecider, PlannerError
from hybrid import planner as planner_module
from hybrid.grounding import NONE, FiniteTargets, GroundingError
from jev_ultrafast.browser import ActionPaused


def page():
    return {
        "url": "https://example.test/", "title": "Catalog", "text": "Search\nCompleted item",
        "fingerprint": "observed-page", "marker": "private-freshness-sentinel",
        "guards": {"key": "private-freshness-sentinel"},
        "task_browser_scope": {
            "mode": "selected_tab", "requested_urls": [], "allowed_hosts": ["example.test"], "outside_scope": False,
        },
        "actions": [
            {"id": "e1", "kind": "click", "label": "Search", "node": 1},
            {"id": "e2", "kind": "fill", "label": "Query", "node": 2},
            {"id": "wait", "kind": "wait", "label": "Wait"},
        ],
    }


def plan(status="continue", subgoal="Use the visible search control", evidence=""):
    return {
        "status": status, "next_subgoal": subgoal if status == "continue" else "",
        "progress_summary": "Observed the catalog", "completion_evidence": evidence,
    }


def envelope(public_plan):
    return httpx.Response(200, json={
        "model": DEFAULT_MODEL, "choices": [{"finish_reason": "stop", "message": {
            "role": "assistant", "content": json.dumps(public_plan),
            "reasoning": "private-reasoning-sentinel", "reasoning_details": [{"text": "private-reasoning-sentinel"}],
        }}], "provider_debug": "private-provider-sentinel",
    })


def click():
    return {"operation": "CLICK", "choice": "e1", "target": "1", "model": "typesafe/jev-1.13"}


def terminal(operation="DONE", reason=None):
    return {"operation": operation, "choice": operation, "stop_reason": reason, "model": "typesafe/jev-1.13"}


def history(count, changed=True):
    return [{"step": index + 1, "operation": "CLICK", "kind": "click", "url": "https://example.test/",
             "action": "Inspect item", "page_changed": changed} for index in range(count)]


@pytest.fixture(autouse=True)
def forbid_live_work(monkeypatch):
    from jev_ultrafast import model

    monkeypatch.delenv("CTRL_PLANNER_MODEL", raising=False)
    monkeypatch.setattr(planner_module, "get_openrouter_key", lambda: "synthetic-secret-sentinel")
    monkeypatch.setattr(planner_module.CLIENT, "post", Mock(side_effect=AssertionError("Unexpected HTTP request")))
    monkeypatch.setattr(model, "get_openrouter_key", Mock(side_effect=AssertionError("Unexpected credential request")))
    monkeypatch.setattr(model.CLIENT, "post", Mock(side_effect=AssertionError("Unexpected Jev request")))
    monkeypatch.setattr(model, "choose", Mock(side_effect=AssertionError("Unexpected Jev call")))


def configured(monkeypatch, plans=None, decisions=None, cancel_event=None):
    post = Mock(side_effect=[envelope(item) for item in (plans if plans is not None else [plan()])])
    jev = Mock(side_effect=decisions) if decisions is not None else Mock(side_effect=lambda *_args: click())
    monkeypatch.setattr(planner_module.CLIENT, "post", post)
    decider = HybridDecider(jev_choose=jev, cancel_event=cancel_event)
    return decider, post, jev


def test_planner_guidance_does_not_replace_goal_or_authorize_new_typing(monkeypatch):
    decider, post, jev = configured(monkeypatch, [plan(subgoal='Search for "planner invented text"')])
    original_page = page()
    original_goal = 'Search for "user text"'
    result = decider.choose(original_page, original_goal, [], ["explicit text"])
    offered_page, goal, _, values = jev.call_args.args
    assert result == click()
    assert goal == original_goal and values == ("explicit text", "user text")
    assert offered_page["planner_context"]["next_subgoal"] == 'Search for "planner invented text"'
    assert "planner_context" not in original_page
    body = post.call_args.kwargs["json"]
    assert post.call_args.args == (planner_module.ENDPOINT,)
    assert body["max_tokens"] == 2048 and body["reasoning"] == {"effort": "low", "exclude": True}
    assert body["response_format"]["json_schema"]["strict"]
    assert "tools" not in body
    assert "private-freshness-sentinel" not in json.dumps(body)
    assert post.call_count == jev.call_count == 1
    public = json.dumps(decider.snapshot())
    assert all(secret not in public for secret in (
        "synthetic-secret-sentinel", "private-reasoning-sentinel", "private-provider-sentinel",
    ))
    copy = decider.snapshot()
    copy["trace"].clear()
    assert len(decider.snapshot()["trace"]) == 1


def test_planner_refreshes_after_four_actual_actions_not_preview_calls(monkeypatch):
    decider, post, jev = configured(monkeypatch, [plan(), plan()])
    for count in (0, 0, 1, 2, 3):
        decider.choose(page(), "Inspect catalog", history(count))
    assert post.call_count == 1 and jev.call_count == 5
    decider.choose(page(), "Inspect catalog", history(4))
    assert post.call_count == 2
    assert decider.snapshot()["trace"][-1]["reason"] == "action_interval"


def test_no_progress_and_changed_supplied_values_trigger_refresh(monkeypatch):
    decider, post, _ = configured(monkeypatch, [plan(), plan(), plan()])
    decider.choose(page(), "Inspect catalog", [])
    decider.choose(page(), "Inspect catalog", history(1, changed=False))
    decider.choose(page(), "Inspect catalog", history(1, changed=False), ["new exact value"])
    assert post.call_count == 3
    assert [entry["reason"] for entry in decider.snapshot()["trace"]] == [
        "first_step", "no_progress", "context_changed",
    ]


def test_entering_task_page_and_changing_origin_refreshes_planner(monkeypatch):
    decider, post, _ = configured(monkeypatch, [plan(), plan(), plan()])
    decider.choose({**page(), "bootstrap": True}, "Inspect catalog", [])
    decider.choose(page(), "Inspect catalog", history(1))
    regional = page()
    regional["url"] = "https://regional.example.test/"
    decider.choose(regional, "Inspect catalog", history(2))
    assert post.call_count == 3
    assert [entry["reason"] for entry in decider.snapshot()["trace"]] == [
        "first_step", "page_context_changed", "page_context_changed",
    ]


def test_continuing_guidance_survives_new_observations_and_paths_within_one_origin(monkeypatch):
    decider, post, jev = configured(monkeypatch)
    decider.choose({**page(), "observation_id": "first"}, "Inspect catalog", [])
    updated = {**page(), "observation_id": "second", "fingerprint": "changed", "url": "https://example.test/item/2"}
    decider.choose(updated, "Inspect catalog", history(1))
    assert post.call_count == 1 and jev.call_count == 2


@pytest.mark.parametrize("status", ["done", "blocked"])
@pytest.mark.parametrize("changed", [
    {"observation_id": "new-observation"}, {"fingerprint": "new-content"},
    {"url": "https://example.test/unfinished"}, {"target_id": "different-tab"},
])
def test_terminal_evidence_is_not_reused_after_observation_changes(monkeypatch, status, changed):
    decider, post, jev = configured(monkeypatch, [plan(status, evidence="Completed item is visible"), plan()])
    original = {**page(), "observation_id": "first-observation", "target_id": "original-tab"}
    assert decider.choose(original, "Inspect catalog", [])["operation"] == status.upper()
    # Agent rejected the terminal as stale; no browser action or history entry occurred.
    assert decider.choose({**original, **changed}, "Inspect catalog", []) == click()
    assert post.call_count == 2 and jev.call_count == 1
    assert decider.snapshot()["trace"][-1]["reason"] == "terminal_observation_changed"


def test_jev_subgoal_done_replans_original_goal_before_another_finite_choice(monkeypatch):
    decider, post, jev = configured(monkeypatch, [plan(), plan(subgoal="Inspect the next required item")],
                                   [terminal(), click()])
    assert decider.choose(page(), "Inspect all catalog items", []) == click()
    assert post.call_count == 2 and jev.call_count == 2
    for call in jev.call_args_list:
        assert call.args[1] == "Inspect all catalog items"
    last_request = json.loads(post.call_args.kwargs["json"]["messages"][1]["content"])
    assert last_request["original_goal"] == "Inspect all catalog items"
    assert last_request["jev_terminal"]["operation"] == "DONE"


def test_only_whole_task_planner_completion_becomes_done_without_fake_probabilities(monkeypatch):
    decider, post, jev = configured(monkeypatch, [plan(), plan("done", evidence="Completed item is visible")],
                                   [terminal()])
    decision = decider.choose(page(), "Inspect completed item", [])
    assert decision["operation"] == decision["choice"] == "DONE"
    assert decision["decision_source"] == "planner" and decision["confidence"] is None
    assert decision["probabilities"] == {} and decision["audit"]["questions"] == []
    assert decision["model"] == DEFAULT_MODEL
    assert post.call_count == 2 and jev.call_count == 1


def test_repeated_jev_done_without_whole_completion_is_bounded_and_fails_closed(monkeypatch):
    decider, post, jev = configured(monkeypatch, [plan(), plan(), plan()], [terminal(), terminal()])
    with pytest.raises(PlannerError, match="after replanning"):
        decider.choose(page(), "Unfinished multi-step task", [])
    assert post.call_count == 3 and jev.call_count == 2
    with pytest.raises(PlannerError):
        decider.choose(page(), "Unfinished multi-step task", [])
    assert post.call_count == 3


@pytest.mark.parametrize("operation,reason", [("BLOCKED", "sign_in_required"), ("NEEDS_INPUT", "missing_text")])
def test_jev_terminal_refresh_preserves_user_handoff(monkeypatch, operation, reason):
    expected = terminal(operation, reason)
    decider, post, jev = configured(monkeypatch, [plan(), plan()], [expected])
    assert decider.choose(page(), "Inspect catalog", []) == expected
    assert post.call_count == 2 and jev.call_count == 1


@pytest.mark.parametrize("operation", [NONE, "CLICK"])
def test_explicit_none_stops_even_when_planner_suggests_continuing(monkeypatch, operation):
    decider, post, jev = configured(monkeypatch, [plan(), plan()], [{**terminal(operation), "choice": NONE}])
    result = decider.choose(page(), "Inspect catalog", [])
    assert result["operation"] == "BLOCKED" and result["stop_reason"] == "unavailable_control"
    assert post.call_count == 2 and jev.call_count == 1


def test_unknown_id_and_operation_mismatch_never_fall_back(monkeypatch):
    for invalid in ({**click(), "choice": "invented"}, {**click(), "target": "2"}, {**click(), "operation": "WAIT"}):
        decider, _, jev = configured(monkeypatch, decisions=[invalid])
        with pytest.raises(GroundingError):
            decider.choose(page(), "Inspect catalog", [])
        assert jev.call_count == 1


def test_generated_text_cannot_pass_a_supplied_payload_id(monkeypatch):
    decider, _, _ = configured(monkeypatch, decisions=[{
        "operation": "TYPE_TEXT", "choice": "e2", "target": "2@v1", "payload_id": "v1", "text": "invented",
    }])
    with pytest.raises(GroundingError, match="outside the exact"):
        decider.choose(page(), "Inspect catalog", [], ["exact user value"])


@pytest.mark.parametrize("invalid", [
    {**plan(), "selector": "#unsafe"}, {**plan(), "new_navigation": "https://elsewhere.test"},
    {**plan(), "extra_strings": ["generated"]}, {**plan(), "status": "invented"},
    {**plan(), "next_subgoal": ""}, {**plan(), "progress_summary": "x" * 1201},
    {**plan(), "progress_summary": None}, {**plan(), "completion_evidence": "line\nbreak"},
    plan("done"), {**plan("blocked"), "progress_summary": ""},
])
def test_invalid_planner_output_never_reaches_jev(monkeypatch, invalid):
    decider, post, jev = configured(monkeypatch, [invalid])
    with pytest.raises(PlannerError):
        decider.choose(page(), "Inspect catalog", [])
    assert post.call_count == 1 and jev.call_count == 0
    assert decider.snapshot()["current"] is None
    assert decider.snapshot()["trace"][0]["status"] == "error"


@pytest.mark.parametrize("response", [
    httpx.Response(200, content="not-json-private-sentinel"),
    httpx.Response(200, json={"choices": []}),
    httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": "private-sentinel"}}]}),
    httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
        "role": "assistant", "content": '{"status":"done","status":"continue"}',
    }}]}),
    httpx.Response(429, text="private-sentinel"), httpx.Response(503, text="private-sentinel"),
])
def test_provider_errors_are_redacted_and_not_retried(monkeypatch, response):
    decider, post, jev = configured(monkeypatch)
    post.side_effect = [response]
    with pytest.raises(PlannerError) as error:
        decider.choose(page(), "Inspect catalog", [])
    assert post.call_count == 1 and jev.call_count == 0
    public = decider.snapshot()
    assert "private-sentinel" not in str(error.value) + json.dumps(public)
    assert public["current"] is None
    assert public["trace"][0]["status"] == "error"
    assert set(public["trace"][0]) == {
        "sequence", "model", "reason", "action_count", "status", "request_bytes", "latency_ms", "jev_terminal",
    }


def test_transport_timeout_is_redacted_without_retry(monkeypatch):
    decider, post, jev = configured(monkeypatch)
    post.side_effect = httpx.ReadTimeout("synthetic-secret-sentinel")
    with pytest.raises(PlannerError, match="connection failed") as error:
        decider.choose(page(), "Inspect catalog", [])
    assert "synthetic-secret-sentinel" not in str(error.value)
    assert post.call_count == 1 and jev.call_count == 0


@pytest.mark.parametrize("when", ["before", "planner", "jev"])
def test_cancellation_discards_late_results_before_returning_an_action(monkeypatch, when):
    cancel = Event()
    decider, post, jev = configured(monkeypatch, cancel_event=cancel)
    if when == "before":
        cancel.set()
    elif when == "planner":
        def complete(*_args, **_kwargs):
            cancel.set()
            return envelope(plan())
        post.side_effect = complete
    else:
        def choose(*_args):
            cancel.set()
            return click()
        jev.side_effect = choose
    with pytest.raises(ActionPaused):
        decider.choose(page(), "Inspect catalog", [])
    assert post.call_count == (0 if when == "before" else 1)
    assert jev.call_count == (1 if when == "jev" else 0)
    if when == "planner":
        assert decider.snapshot()["trace"][0]["status"] == "cancelled"


def test_planner_budget_is_per_task_and_cannot_be_retried_past_limit(monkeypatch):
    decider, post, _ = configured(monkeypatch, [plan()] * 64)
    for count in range(64):
        decider.choose(page(), "Inspect catalog", history(count, changed=False))
    with pytest.raises(PlannerError, match="64-call"):
        decider.choose(page(), "Inspect catalog", history(64, changed=False))
    assert post.call_count == 64 and decider.snapshot()["call_count"] == 64


def test_scope_expansion_and_bootstrap_completion_are_rejected(monkeypatch):
    decider, _, jev = configured(monkeypatch, [plan(subgoal="Open https://unrequested.example/")])
    with pytest.raises(PlannerError, match="destinations"):
        decider.choose(page(), "Inspect catalog", [])
    jev.assert_not_called()
    decider, _, jev = configured(monkeypatch, [plan("done", evidence="I think it is finished")])
    with pytest.raises(PlannerError, match="before a task page"):
        decider.choose({**page(), "bootstrap": True}, "Inspect catalog", [])
    jev.assert_not_called()


def test_planner_request_compacts_history_and_never_truncates_exact_values(monkeypatch):
    decider, post, _ = configured(monkeypatch)
    decider.choose(page(), "Inspect catalog", history(500))
    context = json.loads(post.call_args.kwargs["json"]["messages"][1]["content"])
    assert len(context["recent_actions"]) == 12
    assert context["prior_progress"]["earlier_action_count"] == 488
    decider, post, jev = configured(monkeypatch)
    with pytest.raises(PlannerError, match="context is too large"):
        decider.choose(page(), "Inspect catalog", [], [str(index).zfill(2) + "x" * 1998 for index in range(32)])
    post.assert_not_called()
    jev.assert_not_called()


def test_configured_model_is_visible_and_invalid_config_fails_before_calls(monkeypatch):
    monkeypatch.setenv("CTRL_PLANNER_MODEL", "provider/another-model")
    assert HybridDecider().snapshot()["model"] == "provider/another-model"
    monkeypatch.setenv("CTRL_PLANNER_MODEL", "synthetic-secret-sentinel")
    with pytest.raises(PlannerError) as error:
        HybridDecider()
    assert "synthetic-secret-sentinel" not in str(error.value)


def test_finite_target_port_preserves_distinct_nodes_and_explicit_none():
    actions = [{"id": "one", "kind": "click", "label": "Same"}, {"id": "two", "kind": "click", "label": "Same"}]
    targets = FiniteTargets(actions)
    assert len(targets.descriptions()) == 2
    assert targets.resolve("two") is actions[1]
    assert targets.resolve(NONE) is None
    with pytest.raises(GroundingError):
        targets.resolve("unoffered")
    for invalid in ([actions[0], actions[0]], [{"id": NONE}], [{"id": ""}]):
        with pytest.raises(GroundingError):
            FiniteTargets(invalid)
