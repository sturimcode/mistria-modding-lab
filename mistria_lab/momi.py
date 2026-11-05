"""Runs the MOMI CLI against the lab copy, and only with arguments known to be safe.

The MOMI CLI has no help flag. Any argument it does not recognize means "install", and an install goes to the
first Steam copy it finds. So this file builds every MOMI command line itself, and safe_args() refuses the rest.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
import zipfile
from pathlib import Path


from .config import Config, momi_search_locations, require, same_path

HOLD = 'Maybe.toml.lab-hold'
MODDED_MARKER = 'assets/gml/scripts/mmapi/mmapi.gml'
INSTALL_TIMEOUT = 900
READ_ONLY_FLAGS = {'--version', '--lint'}
INSTALL_FLAGS = {'--strict-lints', '--fail-on-skip', '--compile-check', 'require', 'on', 'off'}


def safe_args(args: list[str], installing: bool = False) -> list[str]:
    """Allow only known flags. Paths are allowed only directly after --lint."""
    allowed = READ_ONLY_FLAGS | (INSTALL_FLAGS if installing else {'--strict-lints', '--compile-check', 'require', 'on', 'off'})
    if not installing:
        require(args and args[0] in READ_ONLY_FLAGS, f'refusing to run MOMI without --version or --lint: {args}')
    skip = 0
    for i, arg in enumerate(args):
        if skip:
            skip -= 1
            continue
        if arg == '--lint':
            require(not installing and i + 2 < len(args), '--lint needs a mod folder and a pristine archive')
            skip = 2
            continue
        require(arg in allowed, f'refusing to pass {arg!r} to MOMI: unknown arguments start a real install')
    return args


def is_modded(archive: Path) -> bool:
    with zipfile.ZipFile(archive) as z:
        return MODDED_MARKER in z.namelist()


def momi_running() -> bool:
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq ModsOfMistriaInstaller*', '/NH'], capture_output=True, text=True).stdout
    return 'ModsOfMistriaInstaller' in out


def version(cfg: Config) -> str:
    require(cfg.momi_cli.exists(), f'MOMI CLI not found at {cfg.momi_cli}')
    r = subprocess.run([str(cfg.momi_cli), *safe_args(['--version'])], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=60)
    return r.stdout.strip()


def lint(cfg: Config, mod: Path) -> int:
    """Read-only: asks MOMI whether a mod would install. The archive is always named, so Steam is never looked up."""
    require(cfg.pristine.exists(), 'run setup first')
    args = safe_args(['--lint', str(mod), str(cfg.pristine), '--strict-lints', '--compile-check', cfg.compile_check])
    r = subprocess.run([str(cfg.momi_cli), *args], cwd=cfg.game, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=INSTALL_TIMEOUT)
    print(r.stdout + r.stderr)
    return r.returncode


def installs_momi_would_find(cfg: Config) -> list[Path]:
    return [p for p in momi_search_locations() if (p / 'Maybe.toml').exists()]


def preflight(cfg: Config) -> list[Path]:
    """Return the install to hide, or stop if MOMI could pick any folder other than the lab."""
    require(not momi_running(), 'MOMI is running. Close it first.')
    hold = cfg.install_dir / HOLD
    require(not hold.exists(), f'{hold} exists, so an earlier run did not finish. Run: python lab.py recover')
    found = installs_momi_would_find(cfg)
    others = [p for p in found if not same_path(p, cfg.install_dir)]
    require(not others, f'MOMI would also find these game copies: {[str(p) for p in others]}. '
                        'The lab cannot protect them. Remove or rename their Maybe.toml by hand, or install from another PC.')
    return found


def recover(cfg: Config) -> bool:
    hold = cfg.install_dir / HOLD
    if not hold.exists():
        return False
    require(not momi_running(), 'MOMI is running. Wait for it to finish, then run recover again.')
    original = cfg.install_dir / 'Maybe.toml'
    require(not original.exists(), f'both {original} and {hold} exist. Inspect them by hand, or verify the game files in Steam.')
    os.replace(hold, original)
    print('restored', original)
    return True


def run_install(cfg: Config, log: Path) -> None:
    """Install cfg.game/mods into cfg.game/assets.zip, with Steam's Maybe.toml hidden only for this run."""
    found = preflight(cfg)
    hide = bool(found)
    flags = safe_args(['--strict-lints', '--fail-on-skip', '--compile-check', cfg.compile_check], installing=True)
    config_dir = cfg.work / 'momi-config'
    config_dir.mkdir(exist_ok=True)
    env = dict(os.environ, EXIT_ON_COMPLETE='true', MOMI_GAME_CONFIG_DIR=str(config_dir))
    original = cfg.install_dir / 'Maybe.toml'
    hold = cfg.install_dir / HOLD
    lines: list[str] = []
    wrong_target: list[str] = []

    if hide:
        os.replace(original, hold)
    try:
        proc = subprocess.Popen([str(cfg.momi_cli), *flags], cwd=cfg.game, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
        timer = threading.Timer(INSTALL_TIMEOUT, proc.kill)
        timer.start()
        try:
            for line in proc.stdout:
                lines.append(line.rstrip())
                # MOMI prints its choice before it writes anything, so a wrong choice can still be stopped here.
                if line.startswith('Guessed Location:') and not same_path(Path(line.split(':', 1)[1].strip()), cfg.game):
                    wrong_target.append(line.strip())
                    proc.kill()
                    break
            proc.wait()
        finally:
            timer.cancel()
    finally:
        if hide:
            os.replace(hold, original)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines[-25:]))
    print('log:', log, '| exit', proc.returncode)
    require(not wrong_target, f'MOMI chose the wrong folder and was stopped: {wrong_target}')
    require(proc.returncode == 0, 'MOMI reported a failure. The log above gives the reason.')
    # The text MOMI prints can be translated, so the proof is the lab's own archive.
    require(is_modded(cfg.game / 'assets.zip'), 'MOMI finished without modding the lab archive')


def timestamped_log(cfg: Config) -> Path:
    return cfg.logs / f'momi-install-{time.strftime("%Y%m%dT%H%M%S")}.log'


def reset_game_archive(cfg: Config) -> None:
    for p in cfg.game.glob('assets*.zip'):
        p.unlink()
    shutil.copy2(cfg.pristine, cfg.game / 'assets.zip')


