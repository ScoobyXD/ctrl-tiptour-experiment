# Isolated Windows browser experiment

The user's September 19 request explicitly authorizes this separate reasoning-model plus Jev experiment. It supersedes the older Jev-only design for this directory only. The baseline in `C:\Users\Jonat\ctrl` remains Jev-only.

This is a browser-only Windows adaptation, not a runnable build of the upstream macOS Swift application. It has an independent source snapshot, virtual environment, runtime state, API port 8767, and native debugger. Never import or load mutable runtime files from the baseline. Keep the existing AWS secret in process memory only; do not introduce another project's credentials. Only one experiment may own normal Chrome, enforced by the shared process-lifetime browser lease. Preserve normal Chrome, its native approval, profile, and tabs.

The source snapshot starts at CTRL `eda9c07d645cd16d1ab9c4aff51bad794f446738`; any later copied fixes must be recorded in `FOUNDATION.md`. TipTour upstream is pinned in the parent `UPSTREAM_REVISION`. Retain both projects' license notices. Python and WinForms are intentional here because this experiment targets Windows; the parent SwiftUI/build rules apply to the original macOS source, which remains unchanged.

Planner output is advisory bounded data, never browser code, selectors, coordinates, new authority, or new navigation scope. Jev selects only current observed actions. Keep cancellation, stale checks, no automatic mutation replay, and honest verification. Public progress summaries are not hidden reasoning traces. Tests must use synthetic local data unless an explicitly scoped live test is authorized.
