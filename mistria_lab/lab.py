"""The lab's steps: setup, install, launch, call, stop. Each one checks that real files stayed unchanged."""
from __future__ import annotations

import json
import os
import shutil
import time
import zipfile
from pathlib import Path

from . import guard, momi, winapi
from .config import Config, LabStop, is_inside, require

MARKER = '.mistria-lab'
SAVE_ROUTE = 'assets/gml/scripts/Serialization/Serde/SerdeUtils.gml'
SAVE_ANCHOR = 'return game_save_id;'
VERSION_FILE = 'assets/gml/scripts/Serialization/Version.gml'
LAB_DEFAULT_SETTINGS = {
    'send_analytics': False, 'global_volume': 0, 'msc_volume': 0, 'amb_volume': 0, 'sfx_volume': 0,
    'borderless_fullscreen': False, 'window_x': 1280, 'window_y': 720,
}


def redirect_line(cfg: Config) -> str:
    return f'return game_save_id + "/{cfg.profile_name}";'


class Lab:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    # ---- Refuse to run next to another game -----------------------------------------------------------------

    def require_no_game(self) -> None:
        running = winapi.game_processes()
        require(not running, 'a Fields of Mistria process is running, and every copy writes the same log.txt. '
                             f'Close it first: {running}')

    def require_lab_folder(self, folder: Path) -> None:
        """Only delete inside a folder the lab created and marked. See docs/TRAPS.md."""
        require((folder / MARKER).exists(), f'{folder} has no {MARKER} marker, so the lab did not create it. Nothing was deleted.')

    # ---- Setup ----------------------------------------------------------------------------------------------

    def choose_pristine(self) -> Path:
        cfg = self.cfg
        if cfg.pristine_archive != 'auto':
            source = Path(os.path.expandvars(cfg.pristine_archive))
            require(source.exists(), f'{source} not found')
            require(not momi.is_modded(source), f'{source} contains MMAPI, so it has been modded')
            return source
        live, backup = cfg.install_dir / 'assets.zip', cfg.install_dir / 'assets.bak.zip'
        require(live.exists(), f'{live} not found. Check game.install_dir.')
        if not momi.is_modded(live):
            return live
        require(backup.exists(), 'your game is modded and has no assets.bak.zip. In Steam, verify the game files, then run setup. '
                                 'Run MOMI afterwards to put your mods back.')
        with zipfile.ZipFile(live) as a, zipfile.ZipFile(backup) as b:
            require(not momi.is_modded(backup), 'assets.bak.zip is modded too. Verify the game files in Steam.')
            require(a.read(VERSION_FILE) == b.read(VERSION_FILE),
                    'assets.bak.zip comes from an older game version than assets.zip. In Steam, verify the game files, then run setup. '
                    'Run MOMI afterwards to put your mods back.')
        return backup

    def setup(self) -> None:
        cfg = self.cfg
        self.require_no_game()
        require(not cfg.game.exists(), f'{cfg.game} already exists. Delete it by hand to build the lab again.')
        before = guard.snapshot(cfg)
        source = self.choose_pristine()
        digest = guard.sha(source)
        require(not cfg.pristine_sha256 or digest == cfg.pristine_sha256, f'{source} has hash {digest}, not pristine.sha256')
        cfg.work.mkdir(parents=True, exist_ok=True)
        (cfg.work / MARKER).write_text('made by mistria-modding-lab\n', encoding='utf-8')
        print('pristine archive:', source)
        print('sha256:', digest)
        shutil.copy2(source, cfg.pristine)
        (cfg.work / 'pristine.sha256').write_text(digest + '\n', encoding='utf-8')
        cfg.game.mkdir()
        (cfg.game / MARKER).write_text('made by mistria-modding-lab\n', encoding='utf-8')
        for item in cfg.install_dir.iterdir():
            if item.is_file() and item.suffix.lower() != '.zip' and not item.name.startswith('ModsOfMistriaInstaller'):
                shutil.copy2(item, cfg.game / item.name)
        require((cfg.game / 'FieldsOfMistria.exe').exists(), 'FieldsOfMistria.exe not found in the game folder')
        shutil.copy2(cfg.game / 'FieldsOfMistria.exe', cfg.game / cfg.exe_name)
        shutil.copy2(cfg.pristine, cfg.game / 'assets.zip')
        (cfg.game / 'mods').mkdir()
        guard.require_unchanged(before, cfg)
        print('lab copy created at', cfg.game)

    # ---- Install --------------------------------------------------------------------------------------------

    def install(self, mods: list[Path] | None = None) -> None:
        cfg = self.cfg
        mods = mods if mods is not None else cfg.mods
        self.require_no_game()
        self.require_lab_folder(cfg.game)
        require(mods, 'no mods to install. Add folders under [mods] in lab.toml.')
        for mod in mods:
            require((mod / 'manifest.toml').exists(), f'{mod} has no manifest.toml')
        expected = (cfg.work / 'pristine.sha256').read_text(encoding='utf-8').strip()
        require(guard.sha(cfg.pristine) == expected, f'{cfg.pristine} no longer matches its recorded hash. Rebuild the lab.')
        before = guard.snapshot(cfg)
        momi.reset_game_archive(cfg)
        shutil.rmtree(cfg.game / 'mods')
        (cfg.game / 'mods').mkdir()
        for mod in mods:
            shutil.copytree(mod, cfg.game / 'mods' / mod.name)
        momi.run_install(cfg, momi.timestamped_log(cfg))
        self.apply_archive_edits()
        guard.require_unchanged(before, cfg)

    def apply_archive_edits(self) -> None:
        """Change only the lab copy's archive: the save redirect, plus any [[patches]] from lab.toml.

        Each anchor must match exactly once. A game update that moves one stops here rather than guessing.
        """
        cfg = self.cfg
        edits = {SAVE_ROUTE: [(SAVE_ANCHOR, redirect_line(cfg))]}
        for patch in cfg.patches:
            edits.setdefault(patch['file'], []).append((patch['find'], patch['replace']))
        archive, temp = cfg.game / 'assets.zip', cfg.game / 'assets.lab-new.zip'
        with zipfile.ZipFile(archive) as src, zipfile.ZipFile(temp, 'w') as out:
            names = set(src.namelist())
            for name in edits:
                require(name in names, f'{name} is not in the game archive, so this game version may differ')
            for info in src.infolist():
                data = src.read(info)
                if info.filename in edits:
                    text = data.decode('utf-8')
                    for find, replace in edits[info.filename]:
                        require(text.count(find) == 1, f'anchor {find!r} in {info.filename} matched {text.count(find)} times, not once')
                        text = text.replace(find, replace)
                    data = text.encode('utf-8')
                out.writestr(info, data)
        self.verify_redirect(temp)
        os.replace(temp, archive)
        print('save redirect applied: lab saves go to', cfg.profile)

    def verify_redirect(self, archive: Path | None = None) -> None:
        archive = archive or self.cfg.game / 'assets.zip'
        with zipfile.ZipFile(archive) as z:
            require(z.testzip() is None, f'{archive} failed its integrity test')
            require(redirect_line(self.cfg) in z.read(SAVE_ROUTE).decode('utf-8'),
                    'the lab archive is not redirected, so saves would reach your real folder. Refusing to continue.')

    def sync(self, mod: Path) -> None:
        """Copy changed .gml files of one installed mod into the lab archive. Add or rename files with install."""
        cfg = self.cfg
        self.require_no_game()
        source = {p.name: p.read_bytes() for p in (mod / 'gml').rglob('*.gml')}
        require(source, f'{mod} has no gml files')
        archive, temp = cfg.game / 'assets.zip', cfg.game / 'assets.sync-new.zip'
        replaced = []
        with zipfile.ZipFile(archive) as src, zipfile.ZipFile(temp, 'w') as out:
            for info in src.infolist():
                data = src.read(info)
                base = info.filename.rsplit('/', 1)[-1]
                if info.filename.startswith('assets/gml/scripts/') and mod.name.lower() in info.filename.lower() and base in source:
                    data = source[base]
                    replaced.append(base)
                out.writestr(info, data)
        if not replaced:
            temp.unlink()
            raise LabStop(f'found no scripts of {mod.name} in the lab archive. Run install.')
        self.verify_redirect(temp)
        os.replace(temp, archive)
        print('synced', sorted(replaced))

    # ---- Lab profile ----------------------------------------------------------------------------------------

    def prepare_profile(self) -> None:
        cfg = self.cfg
        cfg.debug_dir.mkdir(parents=True, exist_ok=True)
        (cfg.profile / MARKER).write_text('made by mistria-modding-lab\n', encoding='utf-8')
        settings_file = cfg.profile / 'settings.json'
        data = {'settings': {}}
        if settings_file.exists():
            data = json.loads(settings_file.read_text(encoding='utf-8-sig'))
        else:
            real = cfg.profile_root / 'settings.json'
            if real.exists():
                # Only the file format version is taken from the real settings file. Nothing is written back.
                version = json.loads(real.read_text(encoding='utf-8-sig')).get('version')
                if version is not None:
                    data['version'] = version
        data.setdefault('settings', {}).update(LAB_DEFAULT_SETTINGS)
        data['settings'].update(cfg.settings)
        settings_file.write_text(json.dumps(data), encoding='utf-8')
        (cfg.debug_dir / 'mmapi.json').write_text(json.dumps({'debug_enabled': True}), encoding='utf-8')

    def reset_profile(self) -> None:
        """Delete the lab's saves and settings. This refuses any folder the lab did not mark as its own."""
        cfg = self.cfg
        self.require_no_game()
        require(not self.session_file.exists(), 'a lab session is still open. Run: python lab.py stop')
        if not cfg.profile.exists():
            print('nothing to reset')
            return
        require(cfg.profile.parent == cfg.profile_root, 'the lab profile is not directly inside the game profile')
        self.require_lab_folder(cfg.profile)
        shutil.rmtree(cfg.profile)
        print('lab profile deleted:', cfg.profile)

    def save_fixture(self, name: str) -> None:
        """Keep a copy of the lab's saves and mod data under work/fixtures, for later runs."""
        cfg = self.cfg
        self.require_no_game()
        target = cfg.work / 'fixtures' / name
        require(not target.exists(), f'fixture {name} already exists')
        require(any((cfg.profile / 'saves').glob('*')) if (cfg.profile / 'saves').exists() else False,
                'the lab profile has no saves to keep. Make one first.')
        target.mkdir(parents=True)
        for part in ('saves', 'mod_data'):
            if (cfg.profile / part).exists():
                shutil.copytree(cfg.profile / part, target / part)
        print('fixture saved:', target)

    def restore_fixture(self, name: str) -> None:
        cfg = self.cfg
        self.require_no_game()
        source = cfg.work / 'fixtures' / name
        require(source.exists(), f'fixture {name} not found in {source.parent}')
        self.require_lab_folder(cfg.profile)
        for part in ('saves', 'mod_data'):
            if (cfg.profile / part).exists():
                shutil.rmtree(cfg.profile / part)
            if (source / part).exists():
                shutil.copytree(source / part, cfg.profile / part)
        print('fixture restored:', name)

    # ---- Launch and stop ------------------------------------------------------------------------------------

    @property
    def session_file(self) -> Path:
        return self.cfg.work / 'session.json'

    @property
    def hold(self) -> Path:
        return self.cfg.work / 'real-log-hold'

    def launch(self, mode: str, window: str | None = None) -> int:
        cfg = self.cfg
        require(mode in ('new', 'continue', 'menu'), 'mode must be new, continue or menu')
        if self.session_file.exists():
            print('an earlier session did not close; closing it first')
            self.stop()
        self.require_no_game()
        self.require_lab_folder(cfg.game)
        require((cfg.game / cfg.exe_name).exists(), 'run setup first')
        self.verify_redirect()
        before = guard.snapshot(cfg)
        self.prepare_profile()
        # Remove the last run's state, so a call cannot read an old result. Then queue an empty batch to clear old commands.
        state = cfg.debug_dir / 'state.json'
        old_rev = 0
        for name in ('state.json', 'control.json'):
            p = cfg.debug_dir / name
            if p.exists():
                d = json.loads(p.read_text(encoding='utf-8-sig'))
                old_rev = max(old_rev, d.get('applied_rev', 0), d.get('rev', 0))
        if state.exists():
            state.unlink()
        (cfg.debug_dir / 'control.json').write_text(json.dumps({'rev': old_rev + 1, 'commands': []}), encoding='utf-8')
        # Hold the real engine logs. The game overwrites them even with redirected saves.
        self.hold.mkdir(parents=True, exist_ok=True)
        for child in self.hold.iterdir():
            child.unlink()
        for name in guard.ENGINE_FILES:
            if (cfg.profile_root / name).exists():
                shutil.copy2(cfg.profile_root / name, self.hold / name)
        baseline = cfg.work / 'session-baseline.json'
        baseline.write_text(json.dumps(before), encoding='utf-8')
        args = list(cfg.launch_args) + ([] if mode == 'menu' else ['--auto-start', mode])
        env = dict(cfg.env, MISTRIA_LAB='1', MISTRIA_LAB_PROFILE=cfg.profile_name)
        exe = cfg.game / cfg.exe_name
        window = window or cfg.window
        require(window in ('hidden', 'offscreen', 'visible'), 'window must be hidden, offscreen or visible')
        self.session_file.write_text(json.dumps({'window': window, 'mode': mode, 'started': time.time()}), encoding='utf-8')
        if window == 'hidden':
            pid = winapi.start_hidden(exe, args, cfg.game, env)
        else:
            pid = winapi.start_visible(exe, args, cfg.game, env)
            if window == 'offscreen' and not winapi.move_offscreen(pid):
                print('warning: could not find the game window to move it')
        self.session_file.write_text(json.dumps({'pid': pid, 'window': window, 'mode': mode, 'started': time.time()}), encoding='utf-8')
        print(f'launched lab game, pid {pid}, window {window}, mode {mode}')
        return pid

    def lab_processes(self) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
        ours, others = [], []
        for pid, path in winapi.game_processes():
            (ours if path and is_inside(Path(path), self.cfg.game) else others).append((pid, path))
        return ours, others

    def stop(self) -> None:
        """Close the lab game, put the real engine logs back and check the real files."""
        cfg = self.cfg
        ours, others = self.lab_processes()
        for pid, _ in ours:
            winapi.kill(pid)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and self.lab_processes()[0]:
            time.sleep(0.25)
        require(not self.lab_processes()[0], 'the lab game did not close')
        if not self.session_file.exists():
            print('no open lab session')
            return
        require(not others, f'another game is running, so the engine logs are still in use: {others}. '
                            'Close it, then run: python lab.py stop')
        self.restore_engine_files()
        baseline = json.loads((cfg.work / 'session-baseline.json').read_text(encoding='utf-8'))
        guard.require_unchanged(baseline, cfg, skip_engine=True)
        self.session_file.unlink()

    def restore_engine_files(self) -> None:
        cfg = self.cfg
        out = cfg.logs / f'engine-{time.strftime("%Y%m%dT%H%M%S")}'
        out.mkdir(parents=True, exist_ok=True)
        for name in guard.ENGINE_FILES:
            live, held = cfg.profile_root / name, self.hold / name
            if live.exists() and not (held.exists() and guard.sha(live) == guard.sha(held)):
                shutil.copy2(live, out / name)
            if held.exists():
                shutil.copy2(held, live)
            elif live.exists():
                live.unlink()
        baseline = json.loads((cfg.work / 'session-baseline.json').read_text(encoding='utf-8'))
        crash = cfg.profile_root / guard.ENGINE_FOLDER
        if crash.exists():
            for p in crash.rglob('*'):
                key = 'profile/' + p.relative_to(cfg.profile_root).as_posix()
                if p.is_file() and key not in baseline:
                    (out / guard.ENGINE_FOLDER).mkdir(exist_ok=True)
                    shutil.move(str(p), out / guard.ENGINE_FOLDER / p.name)
        print('engine logs from this run:', out)

    def recover(self) -> None:
        momi.recover(self.cfg)
        if self.session_file.exists():
            self.stop()
        print('recover finished')

    # ---- Calling test functions in the running game -----------------------------------------------------------

    def read_state(self) -> dict | None:
        try:
            return json.loads((self.cfg.debug_dir / 'state.json').read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            return None

    def call(self, target: str, args: list | None = None, timeout: float = 60, by_path: bool = False) -> dict:
        """Run one function in the game and return its report: {target, args, result} or {error}.

        A function registered with mmapi_debug_register_fn is called by name. by_path resolves a dotted path instead.
        """
        cfg = self.cfg
        deadline = time.monotonic() + timeout
        state = self.read_state()
        while state is None:
            self.require_game_alive()
            require(time.monotonic() < deadline, 'the game never wrote state.json. Check that a mod with MMAPI is installed.')
            time.sleep(0.2)
            state = self.read_state()
        control_file = cfg.debug_dir / 'control.json'
        queued = json.loads(control_file.read_text(encoding='utf-8-sig')).get('rev', 0)
        while state.get('applied_rev', 0) < queued:
            # The game has not reached the cleared batch yet, for example while the title screen is open.
            self.require_game_alive()
            require(time.monotonic() < deadline, 'debug calls are not running yet. They start once the game object exists, '
                                                 'so wait for the world or use a longer timeout.')
            time.sleep(0.1)
            state = self.read_state() or state
        rev = queued + 1
        command = {'op': 'call', 'args': args or []}
        command['path' if by_path else 'fn'] = target
        temp = cfg.debug_dir / 'control.lab-new.json'
        temp.write_text(json.dumps({'rev': rev, 'commands': [command]}), encoding='utf-8')
        os.replace(temp, control_file)
        want = target if by_path else 'fn:' + target
        while time.monotonic() < deadline:
            state = self.read_state()
            if state and state.get('applied_rev', 0) >= rev:
                report = state.get('last_call') or {}
                require(report.get('target') == want, f'the game answered for {report.get("target")!r}, not {want!r}. Run the call again.')
                return report
            self.require_game_alive()
            time.sleep(0.1)
        raise LabStop(f'no answer for {target} within {timeout}s')

    def require_game_alive(self) -> None:
        require(self.lab_processes()[0], 'the lab game has closed or crashed. Run: python lab.py stop, then read the engine log it reports.')

    def wait_ready(self, fn: str, timeout: float) -> dict:
        """Call a status function until it reports active: true."""
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            state = self.read_state()
            names = {f.get('name') for f in (state or {}).get('functions', [])}
            if fn in names:
                try:
                    last = self.call(fn, timeout=max(5, deadline - time.monotonic()))
                except LabStop:
                    self.require_game_alive()
                    raise
                result = last.get('result')
                if isinstance(result, dict) and result.get('active') is True:
                    return result
            self.require_game_alive()
            time.sleep(1)
        raise LabStop(f'{fn} did not report active: true within {timeout}s. Last answer: {last}')

    def run_suite(self, calls: list[str] | None = None) -> bool:
        """Run suite calls. A call passes when it reports no error and its result has passed: true."""
        cfg = self.cfg
        calls = calls if calls is not None else cfg.suite.calls
        require(calls, 'no calls to run. Add them under [suite] in lab.toml.')
        rows = []
        for target in calls:
            report = self.call(target, timeout=cfg.suite.call_timeout)
            result = report.get('result')
            passed = not report.get('error') and isinstance(result, dict) and result.get('passed') is True
            rows.append({'target': target, 'passed': passed, 'error': report.get('error'), 'result': result})
            print(('PASS ' if passed else 'FAIL ') + target + ('' if passed else '  ' + json.dumps(report)[:800]), flush=True)
        cfg.results.mkdir(parents=True, exist_ok=True)
        out = cfg.results / f'suite-{time.strftime("%Y%m%dT%H%M%S")}.json'
        out.write_text(json.dumps(rows, indent=1), encoding='utf-8')
        print(f'{sum(r["passed"] for r in rows)} of {len(rows)} passed. Results: {out}')
        return all(r['passed'] for r in rows)

    def test(self) -> bool:
        """Launch, wait for the world, run the suite, close the game and check real files."""
        suite = self.cfg.suite
        require(suite.ready_fn, 'set suite.ready_fn in lab.toml')
        self.launch(suite.mode)
        passed = False
        try:
            print('ready:', json.dumps(self.wait_ready(suite.ready_fn, suite.ready_timeout))[:400])
            passed = self.run_suite()
        finally:
            self.stop()
        return passed
