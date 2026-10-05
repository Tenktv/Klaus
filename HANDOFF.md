# KLAUS — Project Handoff & Roadmap

> **How to use this file:** Paste the "System prompt for the next session" block below into a new Claude Code chat
> (working directory: this folder). Everything the next session needs is in this file. Last updated: 2026-10-05.

---

## 0. System prompt for the next session

```
You are continuing development of KLAUS, a voice-controlled desktop assistant for Nikola (one-person web design
studio "Klesro Web", Göppingen, Germany). Read HANDOFF.md in the working directory completely before doing anything.

Rules:
- Talk to Nikola in casual German (du). Code comments in German like the existing code. Never switch to English in replies.
- Work through the roadmap in section 5 in order, unless Nikola says otherwise. Start with Phase A (design).
- Before each phase: tell Nikola in max 5 lines which files you will touch. After each phase: real screenshot of his
  actual screen (not offscreen renders), short German summary, git commit.
- Respect every constraint in section 3 ("Hard rules"). They come from real mistakes.
- Use Claude/Claude Code only when Nikola explicitly says "Claude". Default reasoning/research = Gemini + free search.
- Never spend paid API quota in bulk without asking. Never create multiple accounts to dodge free-tier limits.
- Anything with outside effect (sending, printing, uploading, trading, calling, deleting) needs an explicit
  confirmation through the authorization gate — no exceptions.
```

---

## 1. What Klaus is

A Python desktop app that **replaces the Windows desktop** with a full-screen JARVIS/HAL-style HUD panel and is
controlled **by voice only** (wake word "Klaus"). It also runs Nikola's lead-generation business: finds local
businesses without a website (OpenStreetMap), checks them, writes letters with a personal website draft + QR code,
uploads drafts to his IONOS webspace and prints the letters. Long-term goal: sell Klaus as a product (see section 6).

Owner: Nikola, info@klesro-web.de. Machine: Windows 11, RTX 2070 (8 GB), two monitors, mic "IC 6010".

## 2. Architecture (current state, all working)

| Area | Files | Notes |
|---|---|---|
| App entry | `src/klaus_app.py` | PySide6 6.11. Tray, hotkeys (Strg+Alt+K mute, Strg+Shift+M mic off), taskbar auto-hide, autostart, presence/briefing, `Steuerung`. Start: `.venv\Scripts\pythonw.exe src\klaus_app.py` |
| Voice loop | `src/assistent.py` | `Bruecke` signals (zustand, pegel, nachricht, panel, **holo**, …), `Assistent`: wake word, intents, `briefe_starten`, `leads_suchen` (OSM + map + pipeline popups), `holo()`/`log()` helpers, `Pipeline` class |
| Conversation | `src/gemini_live.py` | Gemini Live (`gemini-3.8-live`, voice "Charon") with function-calling tools: oeffne, google_suche, website_im_panel, widget, design, merken, vergessen, **recherche**, frage_claude (only if user says "Claude"), projekt_bauen, was_verpasst, datei_suchen, in_papierkorb, **leads_suchen**, briefe_erstellen, entwuerfe_hochladen, briefe_drucken, stumm_schalten, gespraech_beenden. Every tool call is logged to the Live-Log popup |
| Brain / memory | `src/gehirn.py` | Persona prompt, Obsidian vault memory (`Documents\Klaus Gedächtnis`), `ClaudeGehirn.frage(text, claude=False)` → default = `recherche`, Claude only with `claude=True` |
| Research (no Claude) | `src/recherche.py` | Web search: Tavily (key in .env, free dev tier ~1000/month) → fallback free `ddgs`; summarised by Gemini text models (tries several, 429-tolerant) → fallback Ollama. `hat_website()` = free domain guessing + search |
| Leads | `src/osm_leads.py` | Overpass (mirrors) + Nominatim, stores lat/lon, `websites_pruefen(fortschritt=…)`, Claude check only with `claude=True` |
| Letters | `src/briefe.py`, `src/vorlagen/*.html`, `src/hochladen.py` | DIN 5008 PDF via QtWebEngine, `--ki gemini` default, SFTP upload (paramiko), print via `os.startfile(...,"print")` |
| Local LLM / TTS / STT | `src/llm.py`, `src/stimme.py`, `src/voice.py` | Ollama qwen2.5:7b; edge-tts "Florian" (fallback); faster-whisper small on GPU |
| Data feeds | `src/daten.py` | weather (open-meteo), RSS news, Yahoo finance, system stats, settings (`data/einstellungen.json`, read BOM-safe), layout (`data/layout.json`, **version 2 = fractions 0..1**) |
| Panel UI | `src/web/dashboard.html` + `klaus.js` (HAL eye canvas `KlausOrb`, themes) + `core.js` (state machine IDLE/LISTENING/THINKING/SPEAKING/EXECUTING/AWAITING_AUTH/DONE/ERROR, effects, debug panel Strg+Alt+D) + `holo.js` (free windows: drag, resize, magnet edges, holo boot/close animation) + `popups.js` (holo popups: log, pipeline, karte, entwurf, connector lines, focus mode, Esc closes) | GridStack was removed. Web widgets are native child QWebEngineViews positioned by `webSetze` |
| Python↔JS bridge | `src/fenster.py` `WebBruecke` | signals incl. `holo(str)`; env `KLAUS_CORE_DEBUG=1` opens debug panel + demo |
| Design mockups | `designs/hud_v1_stark/` (**chosen**), `hud_v2_odyssey/`, `hud_v3_tactical/` | standalone HTML, fonts vendored in `assets/fonts` |

Git: local repo in this folder (no remote). `.env` is git-ignored (contains GEMINI_API_KEY, TAVILY_API_KEY,
OPENWEB_NINJA_API_KEY, SFTP placeholders). Backup layout: `data/layout.raster.json`.

## 3. Hard rules (learned the hard way)

1. Use the project venv `.venv\Scripts\python.exe` — `python` in Git Bash is a different (hermes) venv.
2. **Never write Python with backslash escapes through bash heredocs** (`\n`, `\b` get mangled). Use the Edit/Write
   tools or write a script file to the scratchpad first.
3. **Never write JSON settings with PowerShell `Out-File`** (adds BOM). It once corrupted `einstellungen.json` and
   flipped `taskleiste_original` → taskbar would have stayed hidden. Correct values:
   `{"panel": true, "taskleiste_original": false, "thema": "ironman", "autostart": true}`.
4. Only one Klaus instance at a time (parallel instances corrupt the browser profile). Stop it via
   `Get-CimInstance Win32_Process | ? CommandLine -like "*klaus_app.py*" | % { Stop-Process -Id $_.ProcessId -Force }`.
5. Verify UI with **real screenshots of the screen** (`System.Drawing CopyFromScreen`), not `widget.grab()`.
6. Back up `data/layout.json` before UI tests; check it is unchanged afterwards.
7. Nikola sometimes games (League of Legends) — don't restart Klaus / grab the screen while a game is in front.
8. Claude only on explicit request ("Claude"); default = Gemini + free search. Gemini Google-Search grounding is 429
   on the free tier — don't rely on it.
9. Legal (Germany): no cold e-mails / no automated AI cold calls (UWG §7) → letters are the outreach channel.
   AI must disclose itself in calls (EU AI Act). DSGVO for any stored personal data.
10. Licensing for the product: piper voices (GPL), edge-tts (unofficial endpoint), Marvel names/marks → must be
    replaced before selling. Fish-Speech open weights are **non-commercial** (CC-BY-NC-SA).

## 4. What happened in the last session (2026-10-04)

- Research without Claude: `recherche.py` (Tavily → ddgs → Gemini → Ollama). Found that Malerbetrieb Weis and
  Elektro Elser actually have websites → domain check prevents wrong letters.
- Claude is now opt-in only (voice: "frag Claude …").
- Klaus Core state machine + animations, HAL eye, app ring removed.
- Widgets are now **free holo windows** (no grid), migrated layout v1→v2.
- Holo popups (Live Log, Pipeline, Lead Map, Letter draft) with connector lines + **focus mode** (widgets fade out
  while Klaus works). Voice tool `leads_suchen` drives map + pipeline live; `briefe_starten` streams letters live.
- Calmer eye, glass windows, red theme. Nikola still didn't like the look → 3 design directions built with the
  `frontend-design` skill. **Nikola chose Variant 1 "Stark Holo-Tech"** (`designs/hud_v1_stark/index.html`).

## 5. Roadmap (do in this order)

### Phase A — Apply the chosen design (Stark Holo-Tech) to the real panel  ← START HERE
- Port look from `designs/hud_v1_stark/` into `src/web/` (dashboard.html, klaus.js eye, holo.js/popups.js styles):
  chamfered glass windows, glowing edges, top light reflection, Chakra Petch / Barlow Semi Condensed / JetBrains Mono
  (copy WOFF2 from `designs/hud_v1_stark/assets/fonts` to `src/web/vendor`), eye on lit stage with light cone,
  floor reflection, segment rings, slight 3° tilt of side columns.
- Keep all existing behaviour: free drag/resize, magnet edges, collapse/close, layout persistence (v2 fractions),
  voice panel commands, web widgets (native views), theme variables (other palettes must still work), focus mode,
  state machine, debug panel.
- Also fix the evaluator findings for V1: connector lines too short (place popups farther from the eye), faded widgets
  shining through popups (focus opacity → ~0 + no pointer events), lead-map markers covering town names, weather
  widget overflow, eye glow stronger, small text contrast, remove footer "STARK HOLO-TECH".
- Acceptance: real screenshot idle + work mode looks like the mockup; idle CPU of the panel ≈ unchanged or lower.

### Phase B — Performance & smoother animations
- Measure first (Chrome DevTools via `QTWEBENGINE_REMOTE_DEBUGGING=9222`, or `performance.now()` frame stats).
- One shared `requestAnimationFrame` loop for eye + core fx + popups + map instead of several loops; 30 fps idle,
  60 fps only while active; pause when panel hidden (exists: `window.klausPause`).
- Avoid `backdrop-filter` on many large elements if it costs frames; prefer pre-blurred backgrounds.
- Only `transform`/`opacity` in animations; `will-change` sparingly; canvas sized with devicePixelRatio cap (≤1.5).
- Acceptance: steady 60 fps during work-mode demo on RTX 2070; panel < 3 % CPU idle.

### Phase C — Authorization gate (step 3 of the original plan)
- `src/freigabe.py`: one-time tokens; `hochladen.entwuerfe()`, `hochladen.drucken()`, future send/trade/call
  functions **require** a token issued only by the gate (click "Freigeben" or voice "Freigeben").
- Popup type `auth` (amber, summary: what / to whom / how many), core state AWAITING_AUTH, timeout = cancel.

### Phase D — Lagebericht / intel mode (from Nikola's reference videos)
- Voice "Klaus, Lagebericht": sequence world map with news points → zoom Germany → region Göppingen → market charts
  (existing Yahoo data) → key figures (new leads, letters, what changed since yesterday), Klaus narrates.
- Then "Behind the interface": objective-decomposition graph popup (task nodes light up while Klaus works).
- Then competitor check → friction points → strategy blueprint (circle fills) → feeds into lead letters.

### Phase E — More natural voice
- Evaluate **Fish Audio** (cloud TTS API, very natural German, voice cloning, paid per character) vs. local
  **Fish-Speech / OpenAudio** on the RTX 2070 (non-commercial license → fine for Nikola, not for the product).
- Needs streaming for Gemini Live? Gemini Live already speaks itself (voice "Charon"); a custom TTS only fits the
  local pipeline or a "text mode" of Gemini Live. Decide with Nikola: keep Gemini voice vs. Gemini text + Fish TTS
  (adds latency). Prototype + A/B with Nikola before switching.

### Phase F — Permissions ("Klaus braucht mehr Rechte")
- Today Klaus can: open apps, search files, move to recycle bin (with confirmation), widgets, letters, upload, print.
- Add capabilities with explicit scopes, each logged and confirmable: window management, file move/copy/rename,
  install/uninstall via winget (confirm), system settings (volume, display, Bluetooth), screenshots, clipboard.
- Elevated actions: separate small helper started on demand via UAC (`runas`) for single commands — do NOT run all of
  Klaus as admin. Every elevated action goes through the authorization gate.

### Phase G — Cyber security
- Use Windows Defender instead of a homemade scanner: `Get-MpComputerStatus`, `Start-MpScan -ScanType Quick/Full`,
  `Get-MpThreatDetection`, `Update-MpSignature`. Voice: "Klaus, scan den PC".
- Watchers: suspicious autostart entries, new admin users, firewall state, open ports, unsigned processes with
  network access → security widget + warnings. Optional: check downloaded files (Defender custom scan of path).
- Protect Klaus itself: no secrets in logs, `.env` permissions, tool-call allow-list, prompt-injection guard for web
  content (never execute instructions found on websites).

### Phase H — Calendar & business meetings
- Ask Nikola: Google Calendar or Outlook? Then OAuth integration, voice "Was steht morgen an?", create appointments
  (with confirmation), reminders via briefing.
- Meetings: first step = Klaus as **note-taker** (transcribe with faster-whisper, summary + action items into the
  vault). Later: Klaus speaking in meetings only with disclosure (AI Act) and consent of participants.
- "Video": clarify with Nikola what he meant (Gemini Live video/screen input? video calls? video generation?).

### Phase I — Market analysis & trading
- Read-only first: watchlist, news sentiment per ticker, technical indicators, daily market briefing (data: Yahoo
  finance already used). Paper trading mode with simulated portfolio.
- Real trading only via an official broker API that supports German customers (check: Interactive Brokers API,
  others), **every order through the authorization gate**, hard limits (max order size, daily loss limit), kill switch.
- Show Nikola the saved warning about AI trading bots (memory: trading-bot-warnung). No auto-trading without explicit,
  repeated opt-in. No financial advice claims.

### Phase J — Phone number & calls (postponed, costs money)
- Twilio German number (~1.35 $/month), inbound calls answered by Gemini Live (Media Streams), appointments into
  calendar. Outbound only to people who consented / existing customers (UWG). AI disclosure at call start.

### Phase K — Product / selling Klaus
- Editions (from earlier decision): Basis (gamers/power users) and Pro (freelancers/small firms).
- Pricing ideas from Nikola (to validate):
  1. **Done-for-you**: one-time ~4,000 € setup + monthly fee that covers AI tokens (Klaus-hosted proxy, usage limits).
  2. **Bring-your-own-API**: one-time ~2,000–3,000 €, customer enters own API keys (Gemini/Groq/…), no monthly fee.
- "Not everyone gets the same": license key + per-customer feature flags (modules: leads/letters, trading,
  security, phone, meetings), per-customer persona/voice/branding, update channel.
- Before selling: replace GPL/unofficial components, remove Marvel references, setup wizard, installer, DSGVO docs,
  AVV for hosted proxy, support process.
- Free AI tiers (e.g. Groq free API keys): fine for development/testing with ONE account each. Creating many accounts
  to never hit limits breaks the providers' terms → not for the product; product needs paid keys or BYO keys.

## 6. Open questions for Nikola
- Calendar: Google or Outlook?
- "Video" — what exactly?
- Fish Audio: cloud (paid) or local (free, non-commercial)? Keep Gemini's own voice in live conversations?
- Trading: which broker? Paper trading first OK?
- Still missing in `.env`: KLESRO_ADRESSE, KLESRO_TELEFON, SFTP credentials (letters/upload need them).
