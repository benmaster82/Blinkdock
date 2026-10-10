"""Launch Claude Code in Windows Terminal so the island reflects that session.

    python launch_claude.py [workdir]

The island reads a status file, so you only need the hooks installed once
(python install_hooks.py %USERPROFILE%\\.claude\\settings.json). This launcher is
a convenience: it opens Claude in its own terminal where you work normally.
"""
from __future__ import annotations
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

from config import record_terminal_hwnd
from winfocus import find_session_terminal, terminal_title


def find_claude() -> list[str] | None:
    found = shutil.which('claude.exe') or shutil.which('claude')
    if found:
        return [found]
    roaming = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
    candidate = roaming / 'npm/node_modules/@anthropic-ai/claude-code/bin/claude.exe'
    return [str(candidate)] if candidate.is_file() else None


def _run_child(launch_id: str, workdir: Path) -> int:
    try:
        terminal_title(launch_id)
    except ValueError:
        print('Invalid launch ID.')
        return 1
    claude = find_claude()
    if not claude:
        print('claude not found. Install the CLI, log in, then try again.')
        return 1
    env = {**os.environ, 'CLAUDE_ISLAND_LAUNCH_ID': launch_id}
    return subprocess.call(claude, cwd=str(workdir), env=env)


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] == '--child':
        return _run_child(sys.argv[2], Path(sys.argv[3]))
    workdir = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else Path.cwd()
    if not workdir.is_dir():
        print(f'No such directory: {workdir}')
        return 1
    claude = find_claude()
    if not claude:
        print('claude not found. Install the CLI, log in, then try again.')
        return 1
    terminal = shutil.which('wt.exe')
    if terminal:
        launch_id = secrets.token_hex(8)
        python = Path(sys.executable).with_name('python.exe')
        argv = [terminal, '-w', 'new', 'new-tab', '--title', terminal_title(launch_id),
                '--suppressApplicationTitle', '-d', str(workdir), str(python),
                str(Path(__file__).resolve()), '--child', launch_id, str(workdir)]
    else:
        argv = [*claude]
    print(f'Launching Claude Code in {workdir}')

    subprocess.Popen(argv, cwd=str(workdir))
    if terminal:
        for _ in range(60):  # up to ~6 s for the named window to appear
            time.sleep(0.1)
            hwnd = find_session_terminal(launch_id)
            if hwnd:
                record_terminal_hwnd(hwnd)
                print('Terminal window recorded for quick focus.')
                break
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
