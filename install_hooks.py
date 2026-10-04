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
from pathlib import Path

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
    'Notification': 'waiting',
    'Stop': 'done',
    'SessionEnd': 'offline',
}


def command(state: str) -> str:
    return f'"{PYTHON}" "{BRIDGE}" {state}'


def hooks_block() -> dict:
    block: dict[str, list] = {}
    for event, state in EVENTS.items():
        entry = {'hooks': [{'type': 'command', 'command': command(state)}]}
        if event in ('PreToolUse', 'PostToolUse'):
            entry['matcher'] = '*'
        block[event] = [entry]
    return block


def is_island_entry(entry: dict) -> bool:
    return any(str(h.get('command', '')).find('hook_bridge.py') != -1
               for h in entry.get('hooks', []) if isinstance(h, dict))


def merge(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    settings: dict = {}
    if target.exists():
        shutil.copy2(target, target.with_suffix(target.suffix + '.bak'))
        try:
            settings = json.loads(target.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            settings = {}
    hooks = settings.setdefault('hooks', {})
    for event, entries in hooks_block().items():
        existing = [e for e in hooks.get(event, []) if not (isinstance(e, dict) and is_island_entry(e))]
        hooks[event] = existing + entries
    target.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Hooks installed in {target}')
    if target.with_suffix(target.suffix + '.bak').exists():
        print(f'Backup: {target.with_suffix(target.suffix + ".bak")}')


def remove(target: Path) -> None:
    if not target.exists():
        print('No settings.json to clean up.')
        return
    try:
        settings = json.loads(target.read_text(encoding='utf-8'))
    except (ValueError, OSError):
        print('settings.json is not readable: no changes made.')
        return
    hooks = settings.get('hooks', {})
    for event in list(hooks):
        kept = [e for e in hooks[event] if not (isinstance(e, dict) and is_island_entry(e))]
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks:
        settings.pop('hooks', None)
    target.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Island hooks removed from {target}')


def main() -> None:
    if len(sys.argv) > 2 and sys.argv[1].lower() == 'remove':
        remove(Path(sys.argv[2]).expanduser())
    elif len(sys.argv) > 1:
        merge(Path(sys.argv[1]).expanduser())
    else:
        print(json.dumps({'hooks': hooks_block()}, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
