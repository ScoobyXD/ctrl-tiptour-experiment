# [CTRL] Hybrid experiment

This is a separate Windows browser adaptation inspired by TipTour. It is experimental. The original TipTour app in the parent directory requires macOS and remains unchanged.

A reasoning model proposes a bounded next subgoal and public progress summary. Jev chooses exact controls from the current page. The copied CTRL executor checks scope, freshness, cancellation, and rendering readiness before delivering each action. Planner outputs cannot supply JavaScript, selectors, coordinates, new destinations, or new permission.

## Run

Double-click this directory's **Start CTRL.cmd**, or choose **Hybrid experiment** in the baseline's **Choose CTRL.cmd** window. From PowerShell:

```powershell
Set-Location -LiteralPath 'C:\Users\Jonat\ctrl-experiments\tiptour-windows\windows-browser'
.\Start-CTRL.ps1
```

The native Windows debugger talks only to this experiment's backend at `127.0.0.1:8767`. Its environment, runtime directories, traces, session token, and server process are separate from the baseline at port 8766. No task resumes automatically.

Only one experiment can own normal Chrome. Stop the current app before pressing **Connect Chrome** in the other one. Chrome may request its own **Allow** approval for each new backend connection. The experiment preserves your existing Chrome profile and tabs. There is no second browser profile, headless browser, or embedded browser.

Use Run, Pause, Cancel task, Restart task, or Single step in the debugger. **STOP HYBRID** and **Ctrl+Alt+Shift+H** stop only this experiment. Baseline CTRL uses its separate Stop control and Ctrl+Alt+Shift+S.

## Models and evidence

The default planner is `google/gemini-3.1-pro-preview` through OpenRouter chat completions. Jev uses `typesafe/jev-1.13` through OpenRouter Decisions. Set the nonsecret `CTRL_PLANNER_MODEL` environment variable before launch to try another compatible OpenRouter model. The selected identifier appears in planner evidence; an unsupported model or response stops the task rather than silently falling back.

The existing authorized OpenRouter secret is read directly from AWS Secrets Manager into this process's memory. No key is copied from baseline runtime files, written to disk, or sent to the native UI. AWS is credential storage only. Both models receive bounded task-relevant page text; no screenshots are sent.

Planner calls are limited to 64 per task, with 2,048 output tokens per call. Plans refresh as actions progress and at terminal decisions. Jev's actual returned probabilities remain visible separately from the planner's public subgoal, progress summary, and completion evidence. There are no fabricated probabilities or hidden reasoning transcripts. A model's completion claim still needs checking against the final page.

This first experiment types only exact user-supplied strings. Quote search or form text, or add it under Exact text to enter. It does not yet compose email, post text, or arbitrary prose. It supports the copied browser executor's visible DOM controls; macOS voice, OCR, native-app control, and Apple Notes are not ported.

## Development and verification

```powershell
uv sync --locked --python 3.12
uv run pytest -q
uv run ruff check .
powershell.exe -NoProfile -STA -File scripts/Debug-CTRL.ps1 -VerifyOnly
uv build
```

The fixture server in this experiment uses port 8887 and its test driver targets only port 8767. Run `python scripts/browser_lab.py serve`, then explicitly run `python scripts/browser_lab.py smoke --run --scenario catalog` with this experiment connected. Offline tests do not prove live browser reliability. See `VERIFICATION.md` for the current result.

Source origins and boundaries are recorded in `FOUNDATION.md`, the parent `UPSTREAM_REVISION`, and `hybrid/NOTICE.md`. The independent baseline remains Jev-only. Nothing from this experiment is merged into baseline main automatically.
