# Windows browser experiment: source review and implementation seam

Reviewed 2026-09-19. This source review preceded the implementation in `windows-browser/`. See that directory's README and VERIFICATION for the current executable experiment and test status.

## User request and isolation

Investigate a separate Windows browser-only experiment based on TipTour, combining an OpenRouter reasoning model with Jev's finite grounded decisions. Establish what upstream already implements, reusable algorithms, portability work, and an implementation boundary. Preserve the existing CTRL application.

- Source repository: https://github.com/milind-soni/tiptour-macos
- Reviewed upstream `main`: **52582467c883d66484542f3be8e259340eb524f1**, also recorded in `UPSTREAM_REVISION`.
- Commit: `Merge pull request #12 from milind-soni/fix/update-cua-swift-driver`, dated 2026-09-19.
- Clean source clone: `C:\Users\Jonat\ctrl-experiments\tiptour-macos`.
- Experiment worktree: `C:\Users\Jonat\ctrl-experiments\tiptour-windows`.
- Experiment branch: `feature/windows-browser`, created from that clone's `main`. The feature branch follows the upstream naming convention.
- These two directories share TipTour Git objects. They share no Git repository or runtime state with `C:\Users\Jonat\ctrl`.

The review read AGENTS.md, README.md, and LICENSE before implementation files. It ran no upstream script, test suite, dependency installation, app, browser connection, credential lookup, or paid model request. Only the public source was cloned. General experiment documentation remains outside the bundled `TipTour` app directory.

## What upstream actually supports

The macOS 14.2+ SwiftUI/AppKit menu-bar app ships **two separately selected modes**, coordinated by `CompanionManager`:

| Existing mode | Actual provider and behavior |
| --- | --- |
| JEV text | `TipTour/Jev/JevClient.swift` calls `https://api.typesafe.ai/v1/systemone`, model `jev-latest`, with a Keychain key. `JevPointerLoop.swift` observes local targets and chooses single, double, or right click. It does not type, generate text, or see screenshots. |
| Gemini realtime | `TipTour/Voice/GeminiLiveClient.swift` connects directly to Google's Gemini Live WebSocket using `models/gemini-3.1-flash-live-preview`. Audio and optional screenshots support one workflow action per turn, including typing, opening apps/URLs, shortcuts, scrolling, plus an Apple Notes convenience tool. |

JEV defaults to 12 actions and takes a final observation after the last allowed action. Its request contains `pick` and `kind` choice heads plus `done` and `absent` probability heads. Completion uses `done >= 0.70`; `__none__` explicitly stops selection. **There is no minimum selected-target probability or absent-score cutoff.** Tests explicitly accept a top target at probability 0.2 and absent score 0.9. A failed action does not trigger clicking the next ranked candidate.

Both modes call the shared engine/workflow/action-driver boundaries. This is not an existing OpenRouter planner feeding Jev: no OpenRouter client or combined reasoning/Jev orchestration was found. The localhost harness exposes engine operations and explicit deterministic sequences; it does not bundle an external planner. Its pointer endpoint explicitly reports that screenshot planning could be added, rather than implementing that planner already.

Source: [JEV client](https://github.com/milind-soni/tiptour-macos/blob/52582467c883d66484542f3be8e259340eb524f1/TipTour/Jev/JevClient.swift), [JEV loop](https://github.com/milind-soni/tiptour-macos/blob/52582467c883d66484542f3be8e259340eb524f1/TipTour/Jev/JevPointerLoop.swift), [Gemini client](https://github.com/milind-soni/tiptour-macos/blob/52582467c883d66484542f3be8e259340eb524f1/TipTour/Voice/GeminiLiveClient.swift), [harness contract](https://github.com/milind-soni/tiptour-macos/blob/52582467c883d66484542f3be8e259340eb524f1/docs/tiptour-agent-contract.md).

## Reusable algorithms and boundaries

| Pinned source file | Reusable idea and adaptation caveat |
| --- | --- |
| [JevGrounding.swift](https://github.com/milind-soni/tiptour-macos/blob/52582467c883d66484542f3be8e259340eb524f1/TipTour/Jev/JevGrounding.swift) | Pure request/decision conversion, local candidate IDs, explicit none, deterministic tie handling, and duplicate descriptions. Translate away from CGPoint. Do not silently inherit its first-200 candidate truncation or weaker distribution checks; preserve legitimate distinct DOM nodes and validate exact candidate keys, finite probabilities, sum, and selected maximum. |
| [JevPointerLoop.swift](https://github.com/milind-soni/tiptour-macos/blob/52582467c883d66484542f3be8e259340eb524f1/TipTour/Jev/JevPointerLoop.swift) | Refresh → finite decision → one engine action → validated outcome → history. Cancellation around awaits, task-level trace ID, terminal reasons, and final observation. Port the state machine; replace AppKit app identity with scoped browser target/document identity. |
| [WorkflowRunner.swift](https://github.com/milind-soni/tiptour-macos/blob/52582467c883d66484542f3be8e259340eb524f1/TipTour/Workflow/WorkflowRunner.swift) | Per-operation UUID suppresses late callbacks after restart; bounded resolution waits and post-action validation. Port these mechanisms, not the whole AX/UI-dependent class. Unchanged visual state is a pause signal, not proof that an action failed or should repeat. |
| [LocalTargetContinuity.swift](https://github.com/milind-soni/tiptour-macos/blob/52582467c883d66484542f3be8e259340eb524f1/TipTour/Perception/LocalTargetContinuity.swift) and [TipTourEngine.swift](https://github.com/milind-soni/tiptour-macos/blob/52582467c883d66484542f3be8e259340eb524f1/TipTour/Core/TipTourEngine.swift) | Same label/source/display, finite positive rectangles, intersection-over-union ≥ 0.6; engine accepts continuity only when exactly one refreshed target matches. Useful for optional visual detection. DOM identity and document generation should remain stronger browser evidence. |
| [TipTourActionDriver.swift](https://github.com/milind-soni/tiptour-macos/blob/52582467c883d66484542f3be8e259340eb524f1/TipTour/Actions/TipTourActionDriver.swift) | Explicit delivery interface is the main replacement seam. Define a browser driver with observe, navigate, finite click/type/select/scroll, validate, and cancel; remove native app/clipboard/Notes operations. |
| [ScreenshotPerceptualHash.swift](https://github.com/milind-soni/tiptour-macos/blob/52582467c883d66484542f3be8e259340eb524f1/TipTour/Perception/ScreenshotPerceptualHash.swift) | Optional 64-bit dHash: 9×8 grayscale, horizontal comparisons, Hamming threshold 5. Useful to avoid redundant planner images; unsuitable as a sole action-freshness or completion check. |
| [JevTests.swift](https://github.com/milind-soni/tiptour-macos/blob/52582467c883d66484542f3be8e259340eb524f1/TipTourTests/JevTests.swift) | Port decision fixtures for none, invented targets/action kinds, duplicate candidates, and probability ties. Add operation/target correlation, cancellation, stale documents, exact text provenance, and compact-history tests. |

The existing browser resolver scans several fixed debugging ports and converts DOM rectangles into global AppKit coordinates. It is a fallback inside a desktop system, not a ready Windows browser-session manager. Reuse label/geometry insights, replace its connection and coordinate assumptions.

## Proposed Windows architecture

**Recommended seam: a new, independently runnable Python browser core under this worktree, retaining upstream Swift as a pinned reference.** Port the small pure decision/state-machine pieces and implement browser-specific interfaces. Bootstrap the browser driver/controller from an explicit, copied and version-pinned CTRL snapshot; record that second source revision alongside TipTour's revision. Use no editable install, symlink, shared Python import, or live call into the baseline application. Do not attempt to compile the SwiftUI app for Windows. The user authorized this dual-model alternative separately; baseline CTRL remains Jev-only.

1. An OpenRouter reasoning adapter turns the user's task and bounded task-relevant observations into a structured next intent and explicit success evidence. It maintains a compact progress ledger. It never supplies executable JavaScript or invented browser coordinates.
2. A browser observer produces fresh, finite candidates with operation, target ID, document generation, label, and scope. Page contents are observations, not task instructions.
3. A separate Jev adapter selects among those candidates, with an explicit unavailable/needs-input result. Bind operation and target/payload semantics; parallel independent answer heads must not be treated as if they observed one another's choices.
4. A deterministic validator and browser driver execute one selected action, rechecking identity, scope, freshness, and cancellation. Reobserve afterward and let the orchestrator evaluate observed progress. Transport failures never automatically replay mutations.
5. A Windows UI displays task status, all offered candidates/probabilities, selected versus executed actions, and cancellation. It receives public observation projections, never provider keys or raw requests. Expose concise structured plans/evidence, not private model reasoning transcripts.

General reasoning can use OpenRouter's [chat-completions interface](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request), which documents reasoning controls and structured response configuration. The exact reasoning model is deliberately unspecified pending capability/latency testing. Jev needs its separate Decisions adapter; substituting an OpenRouter base URL into upstream's `systemone` client is insufficient. The intended Jev route is `/api/alpha/decisions` with `typesafe/jev-1.13`; verify its typed-question contract before live work, especially upstream's `noul` heads. The Decisions reference timed out during this review; no claim of a newly tested provider contract is made here.

Text generation, browser typing, and cross-site task orchestration would be **new hybrid features**. Track whether a payload is an exact user span or a reasoning-model output; Jev only selects payloads already offered to it. A planner does not fix missing observations or confer permission to act outside the task.

## What must be replaced or excluded

AppKit/SwiftUI, AX/ApplicationServices, NSWorkspace app activation, Quartz input, ScreenCaptureKit, CoreML/Vision detection, AVFoundation audio, macOS Keychain, Apple Notes/AppleScript, and TCC permissions are platform-specific. Browser-only scope can omit native detection/audio/Notes initially, using DOM/CDP observations instead.

The Xcode target links CuaDriverCore, Sparkle, and PostHog; Package.resolved also pins their transitive dependencies. Keep the browser experiment's dependency manifest separate. Do not carry over desktop updates, analytics, model assets, or the macOS harness as incidental dependencies. No dependency build was attempted.

## Isolation and validation plan

- Keep future code, fixtures, virtual environment, logs, and config inside this experiment worktree. Do not import CTRL runtime state, reuse its service token/port, alter its shortcuts, or change its checkout.
- Use a separate Python environment, native window, tasks/traces, and configurable loopback endpoint, proposed port **8767** (availability must be checked when starting). Require authentication and explicit public response schemas; the upstream developer harness is not a drop-in security boundary.
- Enforce exclusive browser ownership between the baseline and experiment. Opening an experiment UI must not attach or take over a running baseline task. The ownership mechanism should reject a second owner, with an explicit release/handoff path, rather than stopping the other app automatically.
- Provide a new explicitly configured credential adapter. Do not silently read keys from this machine, the source app's Keychain, or sibling projects. This research has not provisioned or fetched any key.
- Keep a fake browser and mocked provider transports as the first executable implementation. Test task order, missing controls, duplicate labels, stale identity, cancellation during inference, failed mutations, terminal evidence, malformed provider values, and bounded context.
- Then use a synthetic local catalog with an explicitly selected browser target and task-scoped tab/host access. Paid model and real browser trials are separate validation stages, not completed by this review.

The first bounded implementation slices can proceed as follows:

1. Freeze and copy the baseline executor/controller with provenance and a fake browser; assign separate runtime paths, port, UI identity, and ownership contract.
2. Port the `JevGrounding` finite target pool and explicit-none behavior with source/MIT attribution. Test none, invented IDs, ties, duplicates, and overflow without a provider. Do not add geometric fallback to the DOM executor.
3. Add a configurable OpenRouter reasoning adapter that returns a validated structured intent and observable completion criteria. Keep model response handling separate from credentials and browser execution.
4. Add an orchestrator that refreshes observations, asks Jev to bind an intent to finite offered actions, validates/executes once, then records progress. Bound calls, context, replanning, and cancellation; preserve both model audits without private reasoning transcripts.
5. Integrate the separate native task/trace window and run offline replay plus a synthetic catalog comparison. Mac voice, screen OCR, Apple Notes, arbitrary desktop apps, and remote deployment remain outside this browser-only implementation.

## License and current result

The pinned [MIT LICENSE](https://github.com/milind-soni/tiptour-macos/blob/52582467c883d66484542f3be8e259340eb524f1/LICENSE) names Milind Soni (2026) and portions by Farza/Clicky (2025). Retain both copyright notices and the MIT permission notice with copied or substantial portions. Preserve the license file and attribution in any distributed port. Dependency/model-asset licenses remain separate and require inspection before copying those components.

**Feasible as a browser-focused port of the architecture and selected algorithms. Not an existing hybrid, not a Windows build, and not yet benchmarked.** The smallest useful implementation is the independent observer → planner intent → Jev finite selection → validated browser-driver loop with synthetic tests; the macOS UI and perception stack need not come first.
