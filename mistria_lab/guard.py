"""The real-file guard: fingerprints real saves and the Steam install, and reports any change.

Saves, settings and mod data are hashed in full. Steam files use size and modified time, because hashing
a 600 MB archive before and after every step would be slow, and any write changes the modified time.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
from pathlib import Path

from .config import Config, LabStop

# The game writes these to the real profile root even when saves are redirected. See docs/TRAPS.md.
ENGINE_FILES = ('log.txt', 'error_log.json')
ENGINE_FOLDER = 'crash-images'


def sha(path: Path) -> str:
    with open(path, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def ignored_top(cfg: Config, top: str) -> bool:
    if top.lower() == cfg.profile_name.lower():
        return True
    return any(fnmatch.fnmatch(top.lower(), pattern.lower()) for pattern in cfg.ignore_profile_dirs)


def snapshot(cfg: Config) -> dict:
    out: dict = {}
    if cfg.profile_root.exists():
        for p in sorted(cfg.profile_root.rglob('*')):
            rel = p.relative_to(cfg.profile_root).as_posix()
            if not p.is_file() or ignored_top(cfg, rel.split('/', 1)[0]):
                continue
            try:
                out['profile/' + rel] = sha(p)
            except OSError as err:
                raise LabStop(f'could not read {p}: {err}. Close whatever is using it and run the step again.')
    for p in sorted(cfg.install_dir.rglob('*')):
        if p.is_file():
            stat = p.stat()
            out['steam/' + p.relative_to(cfg.install_dir).as_posix()] = [stat.st_size, stat.st_mtime_ns]
    return out


def differences(before: dict, after: dict, skip_engine: bool = False) -> list[str]:
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    if not skip_engine:
        return changed
    engine = {'profile/' + name for name in ENGINE_FILES}
    return [k for k in changed if k not in engine and not k.startswith(f'profile/{ENGINE_FOLDER}/')]


def require_unchanged(before: dict, cfg: Config, skip_engine: bool = False) -> None:
    changed = differences(before, snapshot(cfg), skip_engine)
    if changed:
        raise LabStop('real files changed: ' + json.dumps(changed[:10]) +
                      '. Stop testing and compare them with your own backup before you play.')
    print('guard: real saves and the Steam install are unchanged')
