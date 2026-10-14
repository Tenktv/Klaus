# Klaus personal command center

## Implementation brief
Warm graphite surfaces, ivory typography and restrained champagne accents. The recognizable white light reactor is the visual center. Local Barlow and Chakra fonts only; no paid generation, hosted media or video. Geometry is drawn by the existing canvas reactor.

Preserve Qt bridge IDs, signals, normalized widget layout, native browser bounds and second-screen routing. Change dashboard, conversation, overlay and popups together. Keep data honest: bridge connection, microphone, recording, coach and PC activity come from actual bridge responses. Command palette (Ctrl+K), quick actions and PC timer use supported methods. Focus and compact preferences stay in localStorage, never in the widget layout.

No Python changes, deployment, live app restart, credentials, live browser profile or commits. Verify JavaScript parsing and isolated offline browser rendering with a stub bridge. External evaluator is coordinated by the parent after implementation.

## Delivered behavior

- Shared `command-center.css` styles dashboard, chat, overlay, widget catalog and existing popup types. Local theme names remain compatible, with quieter accents on graphite.
- `command-center.js` provides Ctrl+K search and free text submission, live activity/control center, bridge actions, PC stop/time limit, recording and coach stop. Only actual bridge responses determine status. Missing methods are disabled; stale status is labeled unavailable. Betrieb polling is every five seconds while visible.
- Focus and compact modes persist under `klaus.command-center.v1` in localStorage. Native web views hide during focus or dialogs. Saved normalized widget layout and second-screen routing remain intact.
- The default layout adds a full-width calendar. Existing saved layouts still load unchanged. Below 800 px a clearly labeled compact reactor/control view prevents unreadable widgets without saving a different layout.
- Approval descriptions scroll separately; Freigeben/Abbrechen remain fixed and visible. Expired approvals disable their buttons. Closing the palette does not dismiss an underlying approval.
- The compact overlay fits 360×390. Text chat uses the same input queue as voice. The white canvas reactor stays static in idle; reduced motion disables CSS animations and keeps canvas rendering state-driven.

## Offline verification

Harness: `C:/Users/Nikola/AppData/Local/Temp/playwright-test-klaus-redesign.js`.
It uses a fresh headless Chromium context and intercepts `https://klaus.test/` to local files. All other requests are blocked. The Qt bridge is a test stub; no Klaus process, live browser profile or runtime layout is touched.

Checks: JavaScript parsing (all standalone/inline scripts), bridge quick actions, free text palette dispatch, view persistence, timer values, PC/coach/recording stop, approval decisions, long approval geometry at 1440 and 768 px, palette Escape isolation, second-screen ready signal, chat submission, 360×390 overlay, no infinite idle CSS animation, and polling suppression when bridge visibility is false. No page exceptions in the checked flows.

Screenshots: `C:/Users/Nikola/.codex/visualizations/2026/10/14/01a13c17-8caa-70a1-9c1d-a01a43be7575/`.
`klaus-dashboard-populated-testdata.png` is prominently labeled **ISOLIERTE VORSCHAU · TESTDATEN**. Sample weather, markets, calendar, projects and news exist only in the temporary test harness, never in application files. Other captures cover empty/unavailable data, control center, chat, overlay, second screen and long approval content.

Native Qt stacking, live CPU consumption and real second-monitor interaction require later integration verification by the parent. They were not claimed as live-tested here.

## Stability follow-up

Quiet mode uses `ruheUmschalten()` and the actual `ruhe` boolean. Missing status/method disables the toggle. The control center shows the last speech source/time and whether speech occurred, recording health warnings and duration without text, and premium-AI status plus daily/monthly budget occupancy, limits and separate reservations. No premium activation control or keys are exposed. Budget occupancy may include reservations; the UI explicitly says reservations are not yet billed and does not claim occupancy is a confirmed invoice amount. Missing optional fields are labeled unavailable/not reported, never fabricated as zero.

Confirmed backend semantics: quiet mode blocks all spoken answers (UI: “Aktiv · Antworten nur als Text”); when off, direct answers may speak, while automatic/calendar output remains text by default. Speech is explicitly labeled as the last output attempt, not active speech; Unix seconds are formatted as local time. Daily/monthly budget occupancy includes reservations (“davon reserviert”), not settled invoice amounts. Budget errors (`fehlers`/`fehler`) show unavailable/blocked status and hide potentially stale amounts. Offline assertions cover these meanings.

Only `command-center.js`, `command-center.css` and this document changed for the follow-up. The temporary offline harness verifies absent fields/method, quiet toggle dispatch, speech suppression details, recording warning and separate reservation labels, in addition to the existing input/status smoke tests. `klaus-quiet-budget-testdata.png` is an isolated stub preview, not live data.
