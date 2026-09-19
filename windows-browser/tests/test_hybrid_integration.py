from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_agent import page
from test_model import choice
from test_trace_api import SyntheticAgent

from ctrl import server
from hybrid import agent as hybrid_agent
from jev_ultrafast import agent as base_agent
from jev_ultrafast import model


def test_hybrid_runtime_selects_hybrid_task_factory_and_keeps_local_state(monkeypatch):
    monkeypatch.delenv("CTRL_EXPERIMENT", raising=False)
    monkeypatch.setattr(server.browser_connection, "status", lambda: {"connected": False})
    constructor = Mock(side_effect=SyntheticAgent)
    monkeypatch.setattr(hybrid_agent, "HybridAgent", constructor)
    controller = server.Controller()
    controller.work("start", {"goal": "Inspect synthetic controls", "target_id": "synthetic-tab", "values": []})
    constructor.assert_called_once()
    assert controller.agent is constructor.return_value or isinstance(controller.agent, SyntheticAgent)
    assert controller.error is None
    assert controller.state()["goal"] == "Inspect synthetic controls"


def test_planner_terminal_is_not_misrepresented_as_a_jev_probability(monkeypatch):
    observed = page()
    browser = Mock(observe=Mock(return_value=observed), fresh=Mock(return_value=True))
    monkeypatch.setattr(base_agent, "Browser", Mock(return_value=browser))
    decision = {
        "choice": "DONE", "operation": "DONE", "decision_source": "planner", "target": None,
        "confidence": None, "probabilities": {}, "latency_ms": 10, "usage": {},
        "audit": {"questions": [], "model": "synthetic/planner", "selected": {"operation": "DONE"}},
    }
    decider = SimpleNamespace(
        choose=Mock(return_value=decision), snapshot=lambda: {"model": "synthetic/planner", "call_count": 1},
    )
    monkeypatch.setattr(hybrid_agent, "HybridDecider", lambda: decider)
    agent = hybrid_agent.HybridAgent(None, "Inspect the visible Search page", target_id="synthetic-tab")
    result = agent.command("tick")
    assert result["status"] == "done" and result["stop_reason"].startswith("The planner")
    assert result["planner"]["model"] == "synthetic/planner"
    assert result["last_decision"]["confidence"] is None
    assert agent.trace_store().get(result["latest_trace_id"])["questions"] == []
    browser.act.assert_not_called()


def test_advisory_planner_quotes_cannot_become_authorized_typing(monkeypatch):
    observed = page()
    observed["planner_context"] = {
        "next_subgoal": 'Search for "planner invented text"',
        "progress_summary": "Synthetic advisory context", "completion_evidence": "",
    }
    captured = []

    def respond(_endpoint, _key, body):
        captured.append(body)
        answers = {}
        for name, question in body["questions"].items():
            selected = "DONE" if name == "operation" else next(iter(question["criteria"]))
            answers[name] = choice(question["criteria"], selected)
        return {"answers": answers, "model": model.MODEL}

    monkeypatch.setattr(model, "get_openrouter_key", lambda: "synthetic-key")
    monkeypatch.setattr(model, "post_json", respond)
    model.choose(observed, 'Find "user exact text"', [], [])
    assert captured[0]["state"]["supplied_values"] == {"v1": "user exact text"}
    assert captured[0]["state"]["task"]["goal"] == 'Find "user exact text"'
    assert captured[0]["state"]["task"]["planner_context"] == observed["planner_context"]
    observed["planner_context"]["javascript"] = "not allowed"
    with pytest.raises(ValueError, match="Invalid advisory"):
        model.choose(observed, 'Find "user exact text"', [], [])
    assert len(captured) == 1
