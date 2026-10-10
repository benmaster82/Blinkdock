"""Find and raise the terminal Claude runs in — by window handle, not by title.

Windows Terminal lets the app rewrite the tab title (Claude shows your first
prompt there), so title matching is unreliable. Instead the launcher records the
exact window it opened and the island raises that handle; class- and title-based
lookups are only fallbacks. Windows-only; a no-op elsewhere.
"""
from __future__ import annotations
import re
import sys

# Windows Terminal's top-level window class (stable across titles).
TERMINAL_CLASS = 'CASCADIA_HOSTING_WINDOW_CLASS'
LAUNCH_ID_PATTERN = re.compile(r'[0-9a-f]{16}\Z')
# Never raise the desktop, the taskbar, or a File Explorer window.
EXCLUDED_CLASSES = {'CabinetWClass', 'ExploreWClass', 'Progman', 'WorkerW',
                    'Shell_TrayWnd', 'Shell_SecondaryTrayWnd', 'Windows.UI.Core.CoreWindow'}


def _enumerate(predicate) -> list[int]:
    if sys.platform != 'win32':
        return []
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):  # noqa: ANN001
        if not user32.IsWindowVisible(hwnd):
            return True
        window_class = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, window_class, 256)
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        if length:
            user32.GetWindowTextW(hwnd, buffer, length + 1)
        if predicate(hwnd, window_class.value, buffer.value):
            found.append(int(hwnd))
        return True

    user32.EnumWindows(callback, 0)
    return found


def raise_hwnd(hwnd: int | None) -> bool:
    if sys.platform != 'win32' or not hwnd:
        return False
    import ctypes
    user32 = ctypes.windll.user32
    if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
        return False
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    return bool(user32.SetForegroundWindow(hwnd))


def find_terminals() -> list[int]:
    """Visible Windows Terminal windows, top of the Z-order first."""
    return _enumerate(lambda _h, cls, _t: cls == TERMINAL_CLASS)


def terminal_title(launch_id: str) -> str:
    if not LAUNCH_ID_PATTERN.fullmatch(launch_id):
        raise ValueError('Invalid Claude Island launch ID')
    return f'Claude Code [{launch_id}]'


def find_session_terminal(launch_id: str) -> int | None:
    """Return a window only when its pinned launch title identifies it uniquely."""
    if not LAUNCH_ID_PATTERN.fullmatch(launch_id):
        return None
    marker = terminal_title(launch_id)
    matches = _enumerate(lambda _h, cls, title: cls == TERMINAL_CLASS
                         and marker in title)
    return matches[0] if len(matches) == 1 else None


def raise_session_terminal(launch_id: str) -> bool:
    return raise_hwnd(find_session_terminal(launch_id))


def raise_window(substring: str) -> bool:
    """Fallback: raise the first window whose title contains ``substring``."""
    if not substring:
        return False
    matches = _enumerate(lambda _h, cls, title: cls not in EXCLUDED_CLASSES
                         and substring.lower() in title.lower())
    return raise_hwnd(matches[0]) if matches else False
