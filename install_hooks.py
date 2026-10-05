"""Generate (or install) the Claude Code hooks that drive the island.

    python install_hooks.py              # print the hooks block to paste
    python install_hooks.py <settings>   # merge into a settings.json (with backup)

Typical targets:
    %USERPROFILE%\\.claude\\settings.json   (all sessions)
    <project>\\.claude\\settings.json       (one project)
"""
from __future__ import annotations
import json
import shutil
import sys
import tempfile
from pathlib import Path

from config import NOTIFICATION_STATES

BRIDGE = Path(__file__).with_name('hook_bridge.py').resolve()


def _pythonw() -> Path:
    # Run the hook without a console window, so no black box flashes on every tool.
    executable = Path(sys.executable).resolve()
    windowless = executable.with_name('pythonw.exe')
    return windowless if windowless.exists() else executable


PYTHON = _pythonw()

# Which Claude Code lifecycle event maps to which island state.
EVENTS = {
    'SessionStart': 'idle',
    'UserPromptSubmit': 'working',
    'PreToolUse': 'working',
    'PostToolUse': 'working',
    'PostToolUseFailure': 'working',
    'PermissionRequest': 'waiting',
    'PermissionDenied': 'working',
    'Elicitation': 'waiting',
    'ElicitationResult': 'working',
    'Stop': 'done',
    'StopFailure': 'error',
    'SessionEnd': 'offline',
}


def command(state: str) -> str:
    return f'"{PYTHON}" "{BRIDGE}" {state}'


def hooks_block() -> dict:
    block: dict[str, list] = {}
    for event, state in EVENTS.items():
        entry = {'hooks': [{'type': 'command', 'command': command(state)}]}
        if event in ('PreToolUse', 'PostToolUse', 'PostToolUseFailure',
                     'PermissionRequest', 'PermissionDenied'):
            entry['matcher'] = '*'
        block[event] = [entry]
    block['Notification'] = [
        {'matcher': '|'.join(kind for kind, mapped in NOTIFICATION_STATES.items()
                            if mapped == state),
         'hooks': [{'type': 'command', 'command': command(state)}]}
        for state in dict.fromkeys(NOTIFICATION_STATES.values())
    ]
    return block


def _load_settings(target: Path) -> dict:
    try:
        settings = json.loads(target.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f'{target} is not readable JSON; no changes made') from exc
    if not isinstance(settings, dict):
        raise ValueError(f'{target} must contain a JSON object; no changes made')
    hooks = settings.get('hooks', {})
    if not isinstance(hooks, dict) or any(not isinstance(entries, list) for entries in hooks.values()):
        raise ValueError(f'{target} has an invalid hooks block; no changes made')
    return settings


def _without_island_hooks(entries: list) -> list:
    kept = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get('hooks'), list):
            kept.append(entry)
            continue
        hooks = [hook for hook in entry['hooks']
                 if not (isinstance(hook, dict)
                         and f'"{BRIDGE}"'.casefold() in str(hook.get('command', '')).casefold())]
        if len(hooks) == len(entry['hooks']):
            kept.append(entry)
        elif hooks:
            kept.append({**entry, 'hooks': hooks})
    return kept


def _write_settings(target: Path, settings: dict) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=target.parent,
                                         prefix=target.name + '.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(settings, stream, indent=2, ensure_ascii=False)
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def merge(target: Path) -> None:
    exists = target.exists()
    settings = _load_settings(target) if exists else {}
    hooks = settings.setdefault('hooks', {})
    for event, entries in hooks_block().items():
        hooks[event] = _without_island_hooks(hooks.get(event, [])) + entries
    target.parent.mkdir(parents=True, exist_ok=True)
    if exists:
        shutil.copy2(target, target.with_suffix(target.suffix + '.bak'))
    _write_settings(target, settings)
    print(f'Hooks installed in {target}')
    if exists:
        print(f'Backup: {target.with_suffix(target.suffix + ".bak")}')


def remove(target: Path) -> None:
    if not target.exists():
        print('No settings.json to clean up.')
        return
    settings = _load_settings(target)
    hooks = settings.get('hooks', {})
    for event in list(hooks):
        kept = _without_island_hooks(hooks[event])
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks:
        settings.pop('hooks', None)
    _write_settings(target, settings)
    print(f'Island hooks removed from {target}')


def main() -> None:
    try:
        if len(sys.argv) > 2 and sys.argv[1].lower() == 'remove':
            remove(Path(sys.argv[2]).expanduser())
        elif len(sys.argv) > 1:
            merge(Path(sys.argv[1]).expanduser())
        else:
            print(json.dumps({'hooks': hooks_block()}, indent=2, ensure_ascii=False))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == '__main__':
    main()
