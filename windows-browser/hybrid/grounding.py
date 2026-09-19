"""Finite target/none contract adapted from TipTour's JevGrounding.swift.

Source: milind-soni/tiptour-macos, revision 52582467c883d66484542f3be8e259340eb524f1.
Copyright (c) 2026 Milind Soni. Portions Copyright (c) 2025 Farza (Clicky).
MIT permission and warranty notice is retained in hybrid/NOTICE.md.

Distinct DOM identities are preserved even when labels match. This does not
replace the browser's document identity, freshness, or mutation validation.
"""

NONE = "__none__"


class GroundingError(ValueError):
    pass


class FiniteTargets:
    def __init__(self, actions):
        self.actions = {}
        for action in actions:
            identifier = action.get("id")
            if not isinstance(identifier, str) or not identifier or identifier == NONE or identifier in self.actions:
                raise GroundingError("Observed targets require distinct, nonreserved IDs.")
            self.actions[identifier] = action

    def resolve(self, selected_id):
        # An explicit none ends this selection. Never walk another probability ranking.
        if selected_id == NONE:
            return None
        if not isinstance(selected_id, str) or selected_id not in self.actions:
            raise GroundingError("The selected target was not offered; no action executed.")
        return self.actions[selected_id]

    def descriptions(self):
        return [{"id": identifier, "kind": action["kind"], "label": action.get("label", "")[:400]}
                for identifier, action in self.actions.items()]
