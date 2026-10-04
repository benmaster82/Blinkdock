# Claude Island

A desktop **Dynamic Island** for Claude Code. A frameless, always-on-top pill
docked to the top of the screen: it stays small and calm while Claude works and
**expands** to get your attention when Claude is waiting for input, has finished,
or hit an error — even if the terminal is in the background.

The island is a pure **renderer**: it never talks to Claude. It polls a small JSON
status file that **Claude Code hooks** write through `hook_bridge.py`. So Claude
runs in its own terminal, you work there normally, and the island reflects what
happens. The `claude` command itself is never modified.

---

## How it works

```
   ┌──────────── Dynamic Island (PySide6) ────────────┐
   │  frameless · always-on-top · top-centre · pill    │
   │  non-activating (never steals keyboard focus)     │
   └───────────────────────▲───────────────────────────┘
                           │ polls (every 150 ms)
                  ┌────────┴─────────┐
                  │  status.json     │  {"state", "detail", "ts"}
                  └────────▲─────────┘
                           │ atomic write, one event → one state
                  ┌────────┴─────────┐
                  │  hook_bridge.py  │  ← invoked by Claude Code hooks
                  └────────▲─────────┘
                           │ configured once in settings.json
                  ┌────────┴─────────┐
                  │   Claude Code    │  runs anywhere, you work as usual
                  └──────────────────┘
```

The island and the hook bridge share `config.py`, so they always agree on the
status-file path and the set of states.

---

## States

| State | Appearance | Claude Code event |
| --- | --- | --- |
| `offline` | grey, collapsed | `SessionEnd` |
| `idle` | dim, collapsed | `SessionStart` (ready, listening) |
| `working` | blue ring, breathing | `UserPromptSubmit`, `PreToolUse` |
| `waiting` | **expanded**, amber, pulsing, chime | `Notification` (needs input or permission) |
| `done` | **expanded** green, then collapses | `Stop` (response complete) |
| `error` | **expanded** red | reserved (interrupted turn) |

The elastic open/close morph (collapsed ↔ expanded) and the breathing ring are
driven by `QPropertyAnimation`. `done` auto-reverts to `idle` after 3 seconds.

---

## Requirements

- Windows 10/11
- Python 3.10+ with **PySide6** (`pip install -r requirements.txt`)
- Claude Code CLI (`claude`) installed and logged in
- Windows Terminal (`wt.exe`) recommended, for reliable click-to-focus

The avatar in `assets/clawd.png` is reused from the Trialogo project.

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
- **Click the island → the Claude terminal comes to the front** (see
  *Click-to-focus* below).
- **Single instance**: re-launching never creates a second island.
- **Stuck-session guard**: if a session dies without a `SessionEnd`, the island
  decays from `working` back to `idle` after a quiet spell (`working_timeout`,
  default 240 s) instead of staying stuck on "working".
- **Remembered position** across restarts.

---

## Components

| File | Role |
| --- | --- |
| `island.py` | The pill (PySide6): morph, pulse, status polling, tray icon, mouse/click handling, single-instance guard |
| `hook_bridge.py` | Invoked by the hooks: maps one lifecycle event to one state and atomically writes `status.json` |
| `config.py` | Shared: status-file path, state vocabulary, settings load/save, recorded terminal handle |
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
| `Notification` | `waiting` |
| `Stop` | `done` |
| `SessionEnd` | `offline` |

Manual control:

```powershell
python install_hooks.py                               # print the hooks JSON to paste
python install_hooks.py <settings.json>               # merge into a settings file (with backup)
python install_hooks.py remove <settings.json>        # strip only the island's hooks
```

Typical targets: `%USERPROFILE%\.claude\settings.json` (all sessions) or
`<project>\.claude\settings.json` (one project).

`hook_bridge.py` also reads the event JSON that Claude Code passes on stdin; for
`PreToolUse` it turns the tool name into a readable detail (e.g. "runs a command",
"edits a file"). Under `pythonw`, stdin may be unavailable — in that case the
state still updates, only the extra detail is dropped.

---

## Click-to-focus

Clicking the island raises the terminal Claude runs in. Window titles are
unreliable (Claude rewrites the tab title to your first prompt), so matching is
layered, most precise first:

1. **Exact window handle** recorded by `launch_claude.py` when it opened the
   terminal (stored in `terminal.json`). Validated with `IsWindow`; stale handles
   are skipped.
2. **Windows Terminal window class** (`CASCADIA_HOSTING_WINDOW_CLASS`) — raises a
   Windows Terminal window regardless of its title; top of the Z-order first.
3. **Title substring** (`focus_title`, default `Claude Code`), with File Explorer
   and shell windows excluded so a folder named "claude-…" never matches.

For the most precise focus, launch Claude via the optional launcher, which records
the exact window:

```powershell
python launch_claude.py C:\path\to\project
```

---

## Configuration

User preferences live in `%LOCALAPPDATA%\claude-island\settings.json`:

| Key | Default | Meaning |
| --- | --- | --- |
| `center_x` | `null` | Horizontal centre in pixels; `null` = centre of the screen. Updated when you drag. |
| `top_margin` | `12` | Distance from the top of the work area, in pixels. |
| `chime` | `true` | Soft sound when Claude starts waiting for you. |
| `working_timeout` | `240` | Seconds of silence before `working` decays to `idle`. |
| `focus_title` | `Claude Code` | Fallback title substring for click-to-focus. |

Other files under `%LOCALAPPDATA%\claude-island\`:

- `status.json` — the live state (override its path with the `CLAUDE_ISLAND_STATUS`
  environment variable).
- `terminal.json` — the recorded terminal window handle, if any.

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
- **One shared status file.** With two Claude sessions at once, the latest event
  wins. A planned refinement lets `waiting` win and shows which project it came
  from.
- **`working` is one level.** Finer detail ("runs a command", "edits a file")
  comes from `PreToolUse` only when stdin is available to the hook.
- **Windows only.** Window focus, autostart, the chime, and the launcher are
  Windows-specific; the island renders elsewhere but those features no-op.
