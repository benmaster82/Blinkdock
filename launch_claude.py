"""Launch Claude Code in Windows Terminal so the island reflects that session.

    python launch_claude.py [workdir]

The island reads a status file, so you only need the hooks installed once
(python install_hooks.py %USERPROFILE%\\.claude\\settings.json). This launcher is
a convenience: it opens Claude in its own terminal where you work normally.
"""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from config import record_terminal_hwnd
from winfocus import find_terminals


def find_claude() -> list[str] | None:
    found = shutil.which('claude.exe') or shutil.which('claude')
    if found:
        return [found]
    roaming = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
    candidate = roaming / 'npm/node_modules/@anthropic-ai/claude-code/bin/claude.exe'
    return [str(candidate)] if candidate.is_file() else None


def main() -> None:
    workdir = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else Path.cwd()
    if not workdir.is_dir():
        print(f'No such directory: {workdir}')
        return
    claude = find_claude()
    if not claude:
        print('claude not found. Install the CLI, log in, then try again.')
        return
    terminal = shutil.which('wt.exe')
    if terminal:
        argv = [terminal, '-w', 'new', 'new-tab', '--title', 'Claude Code',
                '-d', str(workdir), *claude]
    else:
        argv = [*claude]
    print(f'Launching Claude Code in {workdir}')

    # Record the terminal window we open so the island can raise it on click,
    # regardless of how Claude later rewrites the title. '-w new' forces a new
    # Windows Terminal window, so it appears as a handle not present before.
    before = set(find_terminals()) if terminal else set()
    subprocess.Popen(argv, cwd=str(workdir))
    if terminal:
        for _ in range(40):  # up to ~4 s for the new window to appear
            time.sleep(0.1)
            appeared = set(find_terminals()) - before
            if appeared:
                record_terminal_hwnd(appeared.pop())
                print('Terminal window recorded for quick focus.')
                break


if __name__ == '__main__':
    main()
