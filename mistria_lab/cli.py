"""Command line for the lab. Run: python lab.py --help"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config, guard, momi, winapi
from .lab import Lab


def init(args) -> int:
    path = Path(args.config)
    if path.exists():
        print(f'{path} already exists. Edit it, or delete it to start over.')
        return 1
    install = Path(args.install_dir) if args.install_dir else config.find_install()
    if install is None or not (install / 'Maybe.toml').exists():
        print('Could not find Fields of Mistria. Run init again with --install-dir "<folder that holds FieldsOfMistria.exe>".')
        return 1
    momi_cli = Path(args.momi) if args.momi else Path('ModsOfMistriaInstaller-cli.exe')
    if not momi_cli.exists():
        print(f'MOMI CLI not found at {momi_cli}. Download ModsOfMistriaInstaller-cli.exe from '
              'https://github.com/Garethp/Mods-of-Mistria-Installer/releases, then run init with --momi "<its path>".')
        return 1
    path.write_text(config.TEMPLATE.format(install=config.toml_path(install), momi=config.toml_path(momi_cli.resolve())),
                    encoding='utf-8')
    print('wrote', path)
    print('game folder:', install)
    print('MOMI CLI:', momi_cli.resolve())
    print('next: python lab.py doctor')
    return 0


def doctor(cfg) -> int:
    problems = 0

    def row(ok, label, detail=''):
        nonlocal problems
        problems += 0 if ok else 1
        print(('ok    ' if ok else 'FIX   ') + label + (f': {detail}' if detail else ''))

    row(sys.version_info >= (3, 11), 'Python 3.11 or newer', sys.version.split()[0])
    row((cfg.install_dir / 'Maybe.toml').exists() or (cfg.install_dir / momi.HOLD).exists(), 'game folder', str(cfg.install_dir))
    row(cfg.profile_root.exists(), 'game profile', str(cfg.profile_root))
    row(cfg.momi_cli.exists(), 'MOMI CLI', str(cfg.momi_cli))
    if cfg.momi_cli.exists():
        print('      MOMI version:', momi.version(cfg))
    row(not (cfg.install_dir / momi.HOLD).exists(), 'no unfinished install', 'run: python lab.py recover' if (cfg.install_dir / momi.HOLD).exists() else '')
    others = [str(p) for p in momi.installs_momi_would_find(cfg) if not config.same_path(p, cfg.install_dir)]
    row(not others, 'one game copy for MOMI to find', ', '.join(others))
    running = winapi.game_processes()
    row(not running, 'no game running', str(running) if running else '')
    row(cfg.game.exists(), 'lab copy built', str(cfg.game) if cfg.game.exists() else 'run: python lab.py setup')
    print('no problems found' if not problems else f'{problems} item(s) to fix')
    return 1 if problems else 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog='lab.py', description='Test Fields of Mistria mods in a separate copy of the game.')
    ap.add_argument('--config', default='lab.toml', help='settings file (default: lab.toml)')
    sub = ap.add_subparsers(dest='command', required=True)
    p = sub.add_parser('init', help='find the game and write lab.toml')
    p.add_argument('--momi', help='path to ModsOfMistriaInstaller-cli.exe')
    p.add_argument('--install-dir', help='game folder, if it is not found automatically')
    sub.add_parser('doctor', help='check the setup; changes nothing')
    sub.add_parser('setup', help='build the separate game copy')
    p = sub.add_parser('lint', help='ask MOMI if a mod would install; changes nothing')
    p.add_argument('mods', nargs='*', type=Path, help='mod folders (default: [mods] in lab.toml)')
    p = sub.add_parser('install', help='install mods into the lab copy from the pristine archive')
    p.add_argument('mods', nargs='*', type=Path, help='mod folders (default: [mods] in lab.toml)')
    p = sub.add_parser('sync', help='copy changed .gml files of one mod into the lab copy')
    p.add_argument('mod', type=Path)
    p = sub.add_parser('launch', help='start the lab game')
    p.add_argument('--mode', default='new', choices=['new', 'continue', 'menu'])
    p.add_argument('--window', choices=['hidden', 'offscreen', 'visible'])
    p = sub.add_parser('call', help='run one registered function in the running lab game')
    p.add_argument('target')
    p.add_argument('--args', default='[]', help='JSON array of arguments')
    p.add_argument('--path', action='store_true', help='treat target as a dotted path, not a registered function name')
    p.add_argument('--timeout', type=float, default=60)
    p = sub.add_parser('suite', help='run the [suite] calls in the running lab game')
    p.add_argument('calls', nargs='*')
    sub.add_parser('test', help='launch, wait for the world, run the suite, close the game')
    sub.add_parser('stop', help='close the lab game, restore engine logs, check real files')
    sub.add_parser('recover', help='finish after a crash: restore Maybe.toml and the engine logs')
    sub.add_parser('check', help='compare real files with the state recorded by the last launch')
    sub.add_parser('reset-profile', help='delete the lab profile (lab saves and settings)')
    p = sub.add_parser('save-fixture', help='keep a copy of the lab saves')
    p.add_argument('name')
    p = sub.add_parser('restore-fixture', help='put a kept copy of the lab saves back')
    p.add_argument('name')
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if sys.platform != 'win32':
        print('This lab runs on Windows only.')
        return 1
    if args.command == 'init':
        return init(args)
    cfg = config.load(Path(args.config))
    lab = Lab(cfg)
    c = args.command
    if c == 'doctor':
        return doctor(cfg)
    if c == 'setup':
        lab.setup()
    elif c == 'lint':
        before = guard.snapshot(cfg)
        code = 0
        for mod in (args.mods or cfg.mods):
            code = max(code, momi.lint(cfg, mod.resolve()))
        guard.require_unchanged(before, cfg)
        return code
    elif c == 'install':
        lab.install([m.resolve() for m in args.mods] or None)
    elif c == 'sync':
        lab.sync(args.mod.resolve())
    elif c == 'launch':
        lab.launch(args.mode, args.window)
    elif c == 'call':
        print(json.dumps(lab.call(args.target, json.loads(args.args), timeout=args.timeout, by_path=args.path), indent=2))
    elif c == 'suite':
        return 0 if lab.run_suite(args.calls or None) else 1
    elif c == 'test':
        return 0 if lab.test() else 1
    elif c == 'stop':
        lab.stop()
    elif c == 'recover':
        lab.recover()
    elif c == 'check':
        baseline = json.loads((cfg.work / 'session-baseline.json').read_text(encoding='utf-8'))
        guard.require_unchanged(baseline, cfg, skip_engine=lab.session_file.exists())
    elif c == 'reset-profile':
        lab.reset_profile()
    elif c == 'save-fixture':
        lab.save_fixture(args.name)
    elif c == 'restore-fixture':
        lab.restore_fixture(args.name)
    return 0


