# Claude Island

A desktop **Dynamic Island** for Claude Code. A frameless, always-on-top pill
docked to the top of the screen: it stays small and calm while Claude works and
**expands** to get your attention when Claude is waiting for input, has finished,
or hit an error — even if the terminal is in the background.

The island is a read-only **observer**: it never talks to Claude. It polls a small set
of per-session JSON files that **Claude Code hooks** write through `hook_bridge.py`.
So Claude runs in its own terminal, you work there normally, and the island
reflects what happens. The `claude` command itself is never modified.

---

## How it works

```
   ┌──────────── Dynamic Island (PySide6) ────────────┐
   │  frameless · always-on-top · top-centre · pill    │
   │  non-activating (never steals keyboard focus)     │
   └───────────────────────▲───────────────────────────┘
                           │ polls (every 150 ms), aggregates all sessions
                  ┌────────┴──────────────┐
                  │  sessions/<id>.json   │  one file per session
                  └────────▲──────────────┘  {"state","detail","project","ts"}
                           │ atomic write, one event → one state
                  ┌────────┴─────────┐
                  │  hook_bridge.py  │  ← invoked by Claude Code hooks
                  └────────▲─────────┘
                           │ configured once in settings.json
                  ┌────────┴─────────┐
                  │   Claude Code    │  one or more sessions, you work as usual
                  └──────────────────┘
```

The island and the hook bridge share `config.py`, so they always agree on the
sessions directory and the set of states. Successful `Edit` and `Write` calls
also write small atomic local records of files touched by each session.

---

## States

| State | Appearance | Claude Code event |
| --- | --- | --- |
| `offline` | grey, collapsed | `SessionEnd` |
| `idle` | dim, collapsed | `SessionStart` (ready, listening) |
| `working` | blue ring, breathing | prompt, tool activity, or resumed work |
| `background` | **expanded**, teal | `Stop` with background tasks still running |
| `waiting` | **expanded**, amber, pulsing, chime | permission, MCP input, or another user action |
| `done` | **expanded** green, then collapses | `Stop` with no background tasks |
| `error` | **expanded** red | `StopFailure` or a disabled quota resume |
| `unknown` | **expanded**, grey | no fresh event for a prolonged period |

The elastic open/close morph (collapsed ↔ expanded) and the breathing ring are
driven by `QPropertyAnimation`. Compact states keep a short text label visible.
`done` auto-reverts to `idle` after 3 seconds.

---

## Requirements

- Windows 10/11
- Python 3.10+ with **PySide6** (`pip install -r requirements.txt`)
- Claude Code CLI (`claude`) installed and logged in
- Windows Terminal (`wt.exe`) recommended, for reliable click-to-focus

The avatar in `assets/clawd.png` is a rasterized version of LobeHub Icons' Claude Code (Clawd) icon. The icon is licensed under the MIT License; see [`assets/LICENSE.lobehub`](assets/LICENSE.lobehub). Source: [LobeHub Icons](https://github.com/lobehub/lobe-icons/blob/master/packages/static-svg/icons/claudecode.svg).

Claude and Claude Code are trademarks of Anthropic. This project is independent and is not affiliated with or endorsed by Anthropic.

---

## Easy install (recommended)

Once:

```powershell
python -m pip install -r requirements.txt
```

Then **double-click `Install.cmd`** (or run `python setup.py`). It:

- installs the hooks into your Claude Code `settings.json` (with a `.bak` backup,
  preserving any hooks you already have);
- enables autostart so the island launches at every Windows login;
- starts the island immediately.

From then on you **use Claude Code exactly as before** — `claude`, with any
subcommand — and the island reacts. The `claude` command and your `PATH` are not
touched. To undo everything: **`Uninstall.cmd`** (or `python setup.py uninstall`).

> The hooks are global, so the island reacts to **every** Claude Code session,
> including the one you may already be using. A session that was already running
> when you installed will pick up the hooks on its next tool call or on restart.

---

## Try it without Claude

In two terminals:

```powershell
python island.py     # the pill at the top of the screen
python demo.py        # cycles it through every state
```

- **Right-click** the island: menu to simulate any state, or quit.
- **Drag** to move it (position is remembered).
- **Double-click**: hides the island to the tray.
- **Tray icon** (near the clock): click to show/hide, right-click to show or quit.

---

## Daily use

After `Install.cmd` there is nothing to launch — the island is always on. Just
use Claude Code. Behaviour that makes it a tool, not a demo:

- **Waiting → a soft chime** alerts you even if the terminal is in the background
  (toggle with the `chime` key in `settings.json`).
- **Click the island → open the session list when several are tracked**; with
  one launcher-linked session, focus its exact terminal (see *Click-to-focus*).
- **Click the number on the island → inspect all tracked sessions**, each with
  its project, state, and time since the last observed event.
- **Click the file icon and count** to inspect files touched by each session.
  The panel separately shows the current Git working-tree status for that
  project. The count covers unique files touched by tracked sessions, not all
  Git changes. A pending edit is shown separately until the tool succeeds.
- **Git is checked only while the file panel is open**, in a separate process.
  Shell commands, other sessions, and your own edits can all affect Git status,
  so project changes are never attributed to one Claude session without a
  successful file-tool event. Non-Git folders still show direct file activity.
- **Single instance**: re-launching never creates a second island.
- **Stuck-session guard**: if a session dies without a `SessionEnd`, the island
  changes from `working` to `unknown` after a quiet spell (`working_timeout`,
  default 240 s). It does not claim the session is idle without evidence.
- **Remembered position** across restarts.

---

## Components

| File | Role |
| --- | --- |
| `island.py` | The pill (PySide6): morph, pulse, status polling, tray icon, mouse/click handling, single-instance guard |
| `hook_bridge.py` | Invoked by the hooks: maps one lifecycle event to one state and atomically writes that session's file |
| `file_activity.py` | Records successful `Edit`/`Write` paths per session as atomic local files; removes them on session end |
| `file_panel.py` | On-demand file view and non-blocking Git status scan |
| `config.py` | Shared: sessions directory, state vocabulary, settings load/save, recorded terminal handle |
| `winfocus.py` | Find and raise the Claude terminal by window handle / class / title (Windows-only) |
| `install_hooks.py` | Generate / install / remove the Claude Code hooks in a `settings.json` |
| `install_autostart.py` | Enable / disable launch at login (per-user `Run` key, no admin) |
| `launch_claude.py` | Optional: open Claude Code in a new Windows Terminal and record its exact window for precise focus |
| `setup.py` | One-shot install / uninstall (hooks + autostart + start) |
| `demo.py` | Cycle the states without Claude, to tune look and motion |
| `Install.cmd` / `Uninstall.cmd` | Double-click wrappers around `setup.py` |
| `Start Island.cmd` | Start the island manually with no console window (`pythonw`) |

---

## Hooks: event → state mapping

`install_hooks.py` writes one command hook per event. Each runs
`pythonw hook_bridge.py <state>` (via `pythonw` so no console window flashes):

| Event | State |
| --- | --- |
| `SessionStart` | `idle` |
| `UserPromptSubmit` | `working` |
| `PreToolUse` | `working` (with the tool name as detail when available) |
| `PostToolUse`, `PostToolUseFailure` | `working` after a tool result; an interrupted tool becomes `unknown` |
| `PermissionRequest` | `waiting` immediately for a foreground permission request |
| `PermissionDenied` | `working` after an auto-mode denial |
| `Elicitation`, `ElicitationResult` | `waiting`, then `working` for MCP input |
| `Notification` | `waiting`, `working`, or `error` according to its type |
| `Stop` | `done`, or `background` if tasks are still running |
| `StopFailure` | `error` for an API failure |
| `SessionEnd` | `offline` |

The `Notification` hooks use type matchers. Permission, MCP input, background
agent input, and stale quota resume requests show `waiting`. Elicitation completion
and quota auto-resume return to `working`; a disabled quota resume shows `error`.
Informational notifications such as `idle_prompt` and `auth_success` are ignored.
After updating an existing installation, re-run `Install.cmd` to refresh the hooks.

Manual control:

```powershell
python install_hooks.py                               # print the hooks JSON to paste
python install_hooks.py <settings.json>               # merge into a settings file (with backup)
python install_hooks.py remove <settings.json>        # strip only the island's hooks
```

Typical targets: `%USERPROFILE%\.claude\settings.json` (all sessions) or
`<project>\.claude\settings.json` (one project).

`hook_bridge.py` reads the event JSON that Claude Code passes on stdin. It uses
`session_id` to keep sessions separate, `notification_type` to verify a matched
notification, and error codes for the red state. On this Windows setup, a piped
payload reaches `pythonw`; if stdin is unavailable elsewhere, the installed
matchers still select notification states but session labels fall back to defaults.

---

## Click-to-focus

The session list has an arrow on rows whose exact Windows Terminal window can be
identified. Click that row to focus its terminal. The optional launcher opens a
dedicated window with a pinned, unique title and passes its launch ID to Claude;
the hooks attach that ID to the session state. A row is clickable only while
exactly one visible Windows Terminal window matches its launch ID. This avoids
switching to the wrong project when several sessions share a name.

To enable exact focus for a session, open it with the launcher:

```powershell
python launch_claude.py C:\path\to\project
```

Sessions started normally with `claude` are still monitored, but their rows have
no exact-focus action. Clicking the pill body with several sessions opens the
list instead of guessing which terminal to raise. With a single unlinked
session, the older best-effort terminal focus remains: last recorded launcher
window, then a Windows Terminal window, then a configured title match.

---

## Configuration

User preferences live in `%LOCALAPPDATA%\claude-island\settings.json`:

| Key | Default | Meaning |
| --- | --- | --- |
| `center_x` | `null` | Horizontal centre in pixels; `null` = centre of the screen. Updated when you drag. |
| `top_margin` | `12` | Distance from the top of the work area, in pixels. |
| `chime` | `true` | Soft sound when Claude starts waiting for you. |
| `working_timeout` | `240` | Seconds of silence before `working` becomes `unknown`. |
| `focus_title` | `Claude Code` | Fallback title substring for click-to-focus. |

Other files under `%LOCALAPPDATA%\claude-island\`:

- `sessions\<session_id>.json` — one live state file per Claude session.
- `terminal.json` — the recorded terminal window handle, if any.
- `settings.lock` — held while the island runs to prevent duplicate instances.

---

## Multiple sessions

Each Claude Code session (keyed by its `session_id`) writes its own file in the
`sessions` directory, so parallel sessions never clobber each other. The island
reads them all every tick and shows the **most urgent** one, by priority:

```
waiting  >  error  >  working  >  done  >  background  >  unknown  >  idle
```

So if one session is working and another is waiting for you, the island goes
amber for the waiting one. It labels the pill with that session's **project**
(the working directory's name). A dedicated number shows how many sessions are
tracked; click it for a status list sorted by urgency. `unknown` sessions still
appear in the count but are clearly marked because their activity cannot be
confirmed. Launcher-linked rows can open their exact terminal. The chime fires
whenever a *new* session starts waiting, even if the
island was already amber for another. A silent `working` session becomes
`unknown` after `working_timeout`; `waiting`, `error`, and `background` become
`unknown` after an hour, as does an inactive `idle` session. A `done` flash
returns to `idle` after three seconds. Session files are retained until
`SessionEnd`; the tray and right-click menus offer **Forget inactive sessions**
for sessions without an event for over an hour.

---

## Uninstall

```powershell
python setup.py uninstall      # or double-click Uninstall.cmd
```

Removes only the island's hooks (your other hooks and settings are kept), disables
autostart, and stops the island. The `claude` command is never affected.

---

## Troubleshooting

- **States don't change when I use Claude.** The hook event names on your build
  may differ from the mapping above. Check `%USERPROFILE%\.claude\settings.json`,
  then adjust the `EVENTS` map in `install_hooks.py` and re-run the merge.
- **The island isn't visible.** Make sure the process is running
  (`pythonw island.py`), or re-run `Install.cmd`. In `idle`/`offline` it is small
  and dim at the top-centre — nudge it with a state to spot it, or drag it.
- **A black console flashes on every tool.** The hooks must use `pythonw`, not
  `python`. Re-run `python install_hooks.py %USERPROFILE%\.claude\settings.json`
  after updating — the command is regenerated with `pythonw`.
- **Click focuses the wrong window.** Launch Claude via `launch_claude.py` so the
  exact terminal is recorded; otherwise the top Windows Terminal window is used.

---

## Known limitations

- **Single agent (Claude Code).** Codex and other agents have no equivalent hooks;
  they would need a coarser state (running / stopped) or a wrapped process.
- **Manual sessions cannot be focused exactly.** Claude Code's hook payload
  identifies the session but not its terminal window. Use `launch_claude.py` for
  exact focus; without Windows Terminal, the launcher cannot create the link.
- **`working` is one level.** Finer detail ("runs a command", "edits a file")
  comes from `PreToolUse` only when stdin is available to the hook.
- **Interrupts and manual permission denial.** Claude Code does not emit a
  corresponding completion hook for every such action. The island updates on the
  next observed event; otherwise it eventually shows `unknown`.
- **Background completion.** A `Stop` payload can report outstanding tasks, but
  later completion notifications do not identify the full remaining task set.
  A silent background state eventually becomes `unknown`.
- **Windows only.** Window focus, autostart, the chime, and the launcher are
  Windows-specific; the island renders elsewhere but those features no-op.
