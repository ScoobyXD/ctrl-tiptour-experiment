# Source boundary

This directory is an independent snapshot of [CTRL](https://github.com/ScoobyXD/ctrl) at `eda9c07d645cd16d1ab9c4aff51bad794f446738`, adapted for the separately requested TipTour-inspired Windows hybrid experiment. Its MIT notice is retained in LICENSE. TipTour's MIT notices remain in the parent LICENSE; attribution for ported finite grounding lives in the hybrid package.

No virtual environment, credential, task state, history, or browser connection was copied. Start this experiment with its own Start CTRL.cmd. The Windows experiment uses port 8767; the baseline uses 8766. A process-lifetime lease prevents simultaneous control of the user's normal Chrome.

The original Swift macOS application remains in the parent source tree and cannot be built or run on Windows. The planner-plus-Jev orchestration is new experimental code; it is not an existing TipTour feature.

Reviewed browser readiness, shared lease, and delayed transport cleanup fixes were copied independently from CTRL `ba1e8b8169058d04890c1ca86db156ecb010b4ed`. This experiment uses its own copies; no runtime imports refer to the baseline checkout. Hybrid orchestration, server factory, native UI, ports, and model configuration are separate changes.
