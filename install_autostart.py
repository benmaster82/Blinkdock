"""Start the island automatically when you log in to Windows.

    python install_autostart.py          # enable
    python install_autostart.py off      # disable

Uses the per-user Run key (no admin rights) and pythonw.exe so no console window
appears at login.
"""
from __future__ import annotations
import sys
from pathlib import Path

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
VALUE_NAME = 'ClaudeIsland'


def pythonw() -> Path:
    executable = Path(sys.executable)
    windowless = executable.with_name('pythonw.exe')
    return windowless if windowless.exists() else executable


def command() -> str:
    return f'"{pythonw()}" "{Path(__file__).with_name("island.py").resolve()}"'


def enable() -> None:
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
    print('Autostart enabled:\n  ' + command())


def disable() -> None:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
        print('Autostart disabled.')
    except FileNotFoundError:
        print('Autostart was not enabled.')


def main() -> None:
    if sys.platform != 'win32':
        print('Available on Windows only.')
        return
    if len(sys.argv) > 1 and sys.argv[1].lower() in ('off', 'disable', 'remove'):
        disable()
    else:
        enable()


if __name__ == '__main__':
    main()
