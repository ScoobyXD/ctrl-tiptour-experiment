"""Per-task hybrid orchestration; the copied executor keeps all browser checks."""

from jev_ultrafast.agent import Agent

from . import HybridDecider


class HybridAgent(Agent):
    def __init__(self, *args, **kwargs):
        self.decider = HybridDecider()
        self.decider.cancel_event = kwargs.get("cancel_event")
        super().__init__(*args, **kwargs)

    def choose_decision(self, page, goal, history, values):
        return self.decider.choose(page, goal, history, values)

    def snapshot(self):
        return {**super().snapshot(), "planner": self.decider.snapshot()}
