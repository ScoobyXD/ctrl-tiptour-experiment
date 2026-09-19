# Hybrid decision adapter

Create one `hybrid.HybridDecider` per task. Its interface is:

```python
decider = HybridDecider(cancel_event=cancel_event)
decision = decider.choose(page, original_goal, completed_history, exact_values)
public_planner_state = decider.snapshot()
```

The optional `model` constructor parameter or nonsecret `CTRL_PLANNER_MODEL` setting selects the planner. Default: `google/gemini-3.1-pro-preview`. The configured model is visible in every snapshot. `PlannerClient` uses OpenRouter chat completions, strict JSON schema, low reasoning effort with reasoning output excluded, 2,048 maximum output tokens, and a 30-second HTTP timeout. It loads the explicitly configured app credential through `ctrl.credentials.get_openrouter_key()`; it does not persist, log, or return the key. There is no provider retry.

The adapter never executes browser input. The copied Agent/Browser retains target identity, task scope, freshness, geometry, cancellation, and exactly-once mutation checks. The existing Jev client remains the exact action selector. Returned nonterminal decisions are its original decisions, checked against the offered action ID and operation/target/payload mapping.

## Planner contract and visibility

The planner returns exactly four bounded fields:

- `status`: `continue`, `done`, or `blocked`.
- `next_subgoal`: nonempty only for `continue`, at most 1,200 characters.
- `progress_summary`: a public factual summary, at most 1,200 characters; required for `blocked`.
- `completion_evidence`: a public observation-based summary, at most 1,200 characters; required for `done`.

Extra properties, malformed JSON, duplicate content keys, partial/refused/tool-call responses, invalid statuses, oversized context, missing completion evidence, new destinations, or a completion claim on bootstrap state fail closed. The JSON schema has no coordinates, selectors, executable commands, navigation targets, or extra typing values. Summary prose is advisory; only the original goal and browser scope grant authority.

Jev receives the unchanged original goal and exact user values. Advisory strings are supplied via `page['planner_context']`, containing only `next_subgoal`, `progress_summary`, and `completion_evidence`; the experiment's model adapter copies them into task context. They never pass through the goal-to-supplied-values parser. **Generated text entry/composition is intentionally unsupported in this first version.**

`snapshot()` returns `model`, `call_count`, `max_calls`, `current`, and `trace`. Each planner trace entry contains sequence, configured model, refresh reason, completed-action count, status, request byte count, latency, optional preceding Jev terminal, and validated public plan fields. Snapshots are deep copies. No API key, request body, raw provider response, or provider reasoning is retained in this trace.

## Scheduling and terminal behavior

Planning runs initially, after entering a task page from bootstrap or changing origin, after four completed actions, after a new no-progress action, after supplied values change or a paused request is resumed, and after every Jev terminal result. Continuing guidance can survive new observations and URL paths within one origin; repeated previews do not count as actions. Terminal plans are tied to their exact observation ID, fingerprint, URL, and tab target. A changed observation forces fresh planning before a terminal can be returned again, including after Agent freshness rejection with unchanged action history. Context contains the last 12 relevant actions plus compact prior counts, bounded page text and candidate labels; full history and private freshness guards are omitted. Exact supplied values are never silently truncated. Requests exceeding 60,000 serialized bytes are rejected.

There are at most 64 planner calls per task. A Jev `DONE` always triggers verification of the original whole task. A continuing planner gets at most one additional Jev decision in that choose call. Repeated Jev completion without whole-task completion fails closed, rather than ending early or looping indefinitely. Jev `BLOCKED`/`NEEDS_INPUT` refresh the planner but preserve the user handoff. Explicit `__none__` always stops that selection and never falls through to a runner-up.

Planner-confirmed terminal results have `decision_source='planner'`, the planner model, null confidence, and empty probability maps/audit questions. They must not be labeled as a Jev probability or action. The public planner trace supplies their evidence. A blocked terminal uses the existing finite stop-reason IDs. The outer Agent still validates page freshness before accepting a terminal result.

`PlannerError` is a redacted RuntimeError and latches failure for this decider. A new task requires a new decider; goals and completed history cannot be reset inside an existing instance. Credential errors retain the credential module's safe error type. Cancellation raises the existing `ActionPaused`, discards late results, and forces fresh planning before a later resumed decision. The synchronous HTTP request can finish before cancellation is observed, but no returned result causes browser input after the cancellation check.

## TipTour port and tests

`hybrid/grounding.py` adapts the finite target/explicit-none contract from TipTour `JevGrounding.swift` at `52582467c883d66484542f3be8e259340eb524f1`; both upstream copyright notices and MIT permission text are retained in `hybrid/NOTICE.md`. The live decision path uses its exact-ID resolver for every browser action and its none resolver for none selections. Distinct DOM controls with identical labels remain distinct, and there is no silent first-N target truncation.

`tests/test_hybrid_decider.py` uses mocked HTTP/Jev responses. It verifies scheduling, whole-task completion, no-progress replanning, bounded calls, explicit none, unknown IDs, operation/payload mismatch, cancellation, redaction, scope, exact-string provenance, and public snapshot isolation. It does not contact a provider, load a real credential, or use Chrome. Provider compatibility and real-browser validation remain separate integration checks.
