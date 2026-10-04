"""Shared configuration: where the status file lives and the state vocabulary.

Both the island (reader) and the hook bridge (writer) import this so they always
agree on the same file path and the same set of states.
"""
from __future__ import annotations
import os
from pathlib import Path

# Visual contract for every state the island can show.
#   accent    : ring / text colour
#   label     : text shown when the pill is expanded
#   expanded  : whether this state opens the pill
#   pulse     : whether the ring breathes
#   auto_idle : seconds after which the state falls back to 'idle' (0 = stay)
STATES: dict[str, dict] = {
    'offline': {'accent': '#5b6472', 'label': 'offline',       'expanded': False, 'pulse': False, 'auto_idle': 0},
    'idle':    {'accent': '#6b7686', 'label': 'listening',     'expanded': False, 'pulse': False, 'auto_idle': 0},
    'working': {'accent': '#5aa0f2', 'label': 'working',       'expanded': False, 'pulse': True,  'auto_idle': 0},
    'waiting': {'accent': '#f2b705', 'label': 'waiting for you', 'expanded': True, 'pulse': True, 'auto_idle': 0},
    'done':    {'accent': '#35c488', 'label': 'done',          'expanded': True,  'pulse': False, 'auto_idle': 3},
    'error':   {'accent': '#ef5350', 'label': 'error',         'expanded': True,  'pulse': False, 'auto_idle': 0},
}

DEFAULT_STATE = 'offline'


def _base_dir() -> Path:
    base = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'claude-island'
    base.mkdir(parents=True, exist_ok=True)
    return base


def sessions_dir() -> Path:
    """Directory of per-session status files — one JSON per Claude session.

    Each session writes its own file (keyed by session id), so concurrent
    sessions never clobber a shared file; the island aggregates them, letting
    `waiting` win (see island.py).
    """
    path = _base_dir() / 'sessions'
    path.mkdir(parents=True, exist_ok=True)
    return path


# User preferences the island remembers between runs.
DEFAULT_SETTINGS = {
    'center_x': None,       # horizontal centre in pixels; None = centre of screen
    'top_margin': 12,       # distance from the top of the work area
    'chime': True,          # soft sound when Claude starts waiting for you
    'working_timeout': 240, # seconds of silence before 'working' decays to 'idle'
    'focus_title': 'Claude Code', # click raises the first window whose title contains this
}


def settings_path() -> Path:
    return _base_dir() / 'settings.json'


def load_settings() -> dict:
    import json
    settings = dict(DEFAULT_SETTINGS)
    try:
        stored = json.loads(settings_path().read_text(encoding='utf-8'))
        if isinstance(stored, dict):
            settings.update({k: stored[k] for k in DEFAULT_SETTINGS if k in stored})
    except (OSError, ValueError, TypeError):
        pass
    return settings


def save_settings(settings: dict) -> None:
    import json
    merged = {k: settings.get(k, DEFAULT_SETTINGS[k]) for k in DEFAULT_SETTINGS}
    settings_path().write_text(json.dumps(merged, indent=2), encoding='utf-8')


def _terminal_file() -> Path:
    return _base_dir() / 'terminal.json'


def record_terminal_hwnd(hwnd: int) -> None:
    """The launcher stores the window handle of the terminal it just opened."""
    import json
    _terminal_file().write_text(json.dumps({'hwnd': int(hwnd)}), encoding='utf-8')


def load_terminal_hwnd() -> int | None:
    import json
    try:
        return int(json.loads(_terminal_file().read_text(encoding='utf-8'))['hwnd'])
    except (OSError, ValueError, TypeError, KeyError):
        return None
