"""One-shot setup: hooks + autostart + island running.

    python setup.py              # install
    python setup.py uninstall    # remove everything

It never touches the `claude` command or the PATH: the island starts itself at
login and stays on, so you use Claude Code as usual and it reacts.
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

import install_autostart
import install_hooks
from config import _base_dir

HERE = Path(__file__).parent.resolve()
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008


def user_settings() -> Path:
    return Path.home() / '.claude' / 'settings.json'


def check_deps() -> bool:
    try:
        import PySide6  # noqa: F401
        return True
    except ImportError:
        print('PySide6 is missing. Run first:')
        print('    python -m pip install -r requirements.txt')
        return False


def start_island() -> None:
    executable = install_autostart.pythonw()
    subprocess.Popen([str(executable), str(HERE / 'island.py')], cwd=str(HERE),
                     creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS)


def stop_island() -> None:
    script = ("Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' OR Name='python.exe'\" | "
              "Where-Object { $_.CommandLine -like '*island.py*' } | "
              "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    subprocess.run(['powershell', '-NoProfile', '-Command', script],
                   capture_output=True, text=True)


def install() -> None:
    if not check_deps():
        return
    install_hooks.merge(user_settings())
    install_autostart.enable()
    (_base_dir() / 'terminal.json').unlink(missing_ok=True)  # drop any stale handle
    stop_island()
    start_island()
    print()
    print('  DONE.')
    print('  - The island is running and restarts itself at every Windows login.')
    print('  - Use Claude Code as usual: the island changes state while you work,')
    print('    turns amber (with a sound) when Claude is waiting, green when it finishes.')
    print('  - Click the island: brings the terminal to the front. Double-click: hides it')
    print('    to the tray. From the tray you can show it again or quit.')
    print('  - To undo everything: Uninstall.cmd')


def uninstall() -> None:
    install_hooks.remove(user_settings())
    install_autostart.disable()
    stop_island()
    print('Removed: hooks, autostart, and the island has been stopped.')


def main() -> None:
    if sys.platform != 'win32':
        print('This setup is for Windows only.')
        return
    try:
        if len(sys.argv) > 1 and sys.argv[1].lower() in ('uninstall', 'off', 'remove'):
            uninstall()
        else:
            install()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == '__main__':
    main()
