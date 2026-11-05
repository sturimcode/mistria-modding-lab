"""Reads lab.toml and finds the game. Nothing in this file writes to the game or its saves."""
from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

GAME_FOLDER = 'Fields of Mistria'
PROFILE_RESERVED = {'saves', 'mods', 'mod_data', 'crash-images'}


class LabStop(SystemExit):
    """A safety check failed. The message says what to do next."""

    def __init__(self, message: str):
        super().__init__('STOP: ' + message)


def require(ok, message: str) -> None:
    if not ok:
        raise LabStop(message)


def same_path(a: Path, b: Path) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def is_inside(child: Path, parent: Path) -> bool:
    child_text = os.path.normcase(os.path.abspath(child))
    parent_text = os.path.normcase(os.path.abspath(parent))
    return child_text == parent_text or child_text.startswith(parent_text.rstrip('\\/') + os.sep)


@dataclass
class Suite:
    ready_fn: str = ''
    calls: list = field(default_factory=list)
    mode: str = 'new'
    ready_timeout: int = 180
    call_timeout: int = 120


@dataclass
class Config:
    path: Path
    install_dir: Path
    profile_root: Path
    momi_cli: Path
    work: Path
    profile_name: str = 'mistria-lab'
    exe_name: str = 'FieldsOfMistriaLab.exe'
    window: str = 'hidden'
    pristine_archive: str = 'auto'
    pristine_sha256: str = ''
    compile_check: str = 'require'
    mods: list = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    launch_args: list = field(default_factory=lambda: ['--story-events=false'])
    env: dict = field(default_factory=dict)
    ignore_profile_dirs: list = field(default_factory=list)
    patches: list = field(default_factory=list)
    suite: Suite = field(default_factory=Suite)

    @property
    def game(self) -> Path:
        return self.work / 'game'

    @property
    def pristine(self) -> Path:
        return self.work / 'pristine-assets.zip'

    @property
    def logs(self) -> Path:
        return self.work / 'logs'

    @property
    def results(self) -> Path:
        return self.work / 'results'

    @property
    def profile(self) -> Path:
        return self.profile_root / self.profile_name

    @property
    def debug_dir(self) -> Path:
        return self.profile / 'mod_data' / 'mmapi'


def load(path: Path) -> Config:
    require(path.exists(), f'{path} not found. Run: python lab.py init --momi <path to ModsOfMistriaInstaller-cli.exe>')
    with open(path, 'rb') as f:
        raw = tomllib.load(f)
    base = path.resolve().parent

    def rooted(text):
        p = Path(os.path.expandvars(str(text)))
        return p if p.is_absolute() else (base / p)

    game = raw.get('game', {})
    momi = raw.get('momi', {})
    lab = raw.get('lab', {})
    guard = raw.get('guard', {})
    pristine = raw.get('pristine', {})
    suite = raw.get('suite', {})
    cfg = Config(
        path=path.resolve(),
        install_dir=rooted(game.get('install_dir', '')),
        profile_root=rooted(game.get('profile_root', r'%LOCALAPPDATA%\FieldsOfMistria')),
        momi_cli=rooted(momi.get('cli', '')),
        compile_check=momi.get('compile_check', 'require'),
        work=rooted(lab.get('work', 'work')),
        profile_name=lab.get('profile_name', 'mistria-lab'),
        exe_name=lab.get('exe_name', 'FieldsOfMistriaLab.exe'),
        window=lab.get('window', 'hidden'),
        launch_args=list(lab.get('launch_args', ['--story-events=false'])),
        env=dict(lab.get('env', {})),
        pristine_archive=str(pristine.get('archive', 'auto')),
        pristine_sha256=str(pristine.get('sha256', '')).lower(),
        mods=[rooted(m) for m in raw.get('mods', {}).get('folders', [])],
        settings=dict(raw.get('settings', {})),
        ignore_profile_dirs=list(guard.get('ignore_profile_dirs', [])),
        patches=list(raw.get('patches', [])),
        suite=Suite(
            ready_fn=suite.get('ready_fn', ''),
            calls=list(suite.get('calls', [])),
            mode=suite.get('mode', 'new'),
            ready_timeout=int(suite.get('ready_timeout', 180)),
            call_timeout=int(suite.get('call_timeout', 120)),
        ),
    )
    validate(cfg)
    return cfg


def validate(cfg: Config) -> None:
    require(re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,48}', cfg.profile_name),
            'lab.profile_name may use only lowercase letters, digits, - and _')
    require(cfg.profile_name not in PROFILE_RESERVED, f'lab.profile_name cannot be {cfg.profile_name}: the real game uses that folder')
    require(re.fullmatch(r'[A-Za-z0-9_-]+\.exe', cfg.exe_name), 'lab.exe_name must be a plain file name ending in .exe')
    require(cfg.window in ('hidden', 'offscreen', 'visible'), 'lab.window must be hidden, offscreen or visible')
    require(cfg.compile_check in ('require', 'on', 'off'), 'momi.compile_check must be require, on or off')
    require(not is_inside(cfg.work, cfg.install_dir), 'lab.work is inside the game folder. Pick a folder outside Steam.')
    require(not is_inside(cfg.work, cfg.profile_root), 'lab.work is inside the game profile. Pick another folder.')
    require(not is_inside(cfg.install_dir, cfg.work), 'lab.work contains the game folder. Pick a dedicated empty folder.')
    for arg in cfg.launch_args:
        require(isinstance(arg, str) and arg.startswith('--') and '--auto-start' not in arg,
                'lab.launch_args entries must be flags; use the --mode option for --auto-start')
    for patch in cfg.patches:
        require(all(isinstance(patch.get(k), str) and patch.get(k) for k in ('file', 'find', 'replace')),
                'each [[patches]] entry needs file, find and replace')


def steam_candidates() -> list[Path]:
    """Steam libraries listed by Steam itself, read from the registry and libraryfolders.vdf."""
    roots: list[Path] = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
            roots.append(Path(winreg.QueryValueEx(key, 'SteamPath')[0]))
    except OSError:
        pass
    found: list[Path] = list(roots)
    for root in roots:
        vdf = root / 'steamapps' / 'libraryfolders.vdf'
        if vdf.exists():
            text = vdf.read_text(encoding='utf-8', errors='replace')
            found += [Path(m.replace('\\\\', '\\')) for m in re.findall(r'"path"\s+"([^"]+)"', text)]
    return found


def momi_search_locations() -> list[Path]:
    """The game folders the MOMI CLI 0.17.0 checks, in its order, before it falls back to its working directory."""
    home = Path(os.path.expanduser('~'))
    steamapps = [Path(r'C:\Program Files (x86)\Steam\steamapps'), Path(r'C:\Program Files\Steam\steamapps'),
                 home / 'steam/steam/steamapps']
    for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        drive = Path(f'{letter}:\\')
        if drive.exists():
            steamapps += [drive / s for s in ('SteamLibrary/steamapps', 'Steam/steamapps', 'Program Files/Steam/steamapps',
                                              'Program Files (x86)/Steam/steamapps', 'Program Files/SteamLibrary/steamapps',
                                              'Program Files (x86)/SteamLibrary/steamapps')]
    return [s / 'common' / GAME_FOLDER for s in steamapps]


def find_install() -> Path | None:
    for lib in steam_candidates():
        candidate = lib / 'steamapps' / 'common' / GAME_FOLDER
        if (candidate / 'Maybe.toml').exists():
            return candidate
    for candidate in momi_search_locations():
        if (candidate / 'Maybe.toml').exists():
            return candidate
    return None


TEMPLATE = """# Created by: python lab.py init. This file holds paths from your own PC, so it is not committed.

[game]
install_dir = {install}
# profile_root = '%LOCALAPPDATA%\\FieldsOfMistria'

[momi]
cli = {momi}
compile_check = "require"   # require, on or off. "require" stops the install if GML does not compile.

[pristine]
archive = "auto"            # or a path to an unmodded assets.zip
# sha256 = ""               # optional: refuse any archive with a different hash

[lab]
work = "work"
profile_name = "mistria-lab"
exe_name = "FieldsOfMistriaLab.exe"
window = "hidden"           # hidden, offscreen or visible
launch_args = ["--story-events=false"]

[mods]
folders = [
  "examples/hello_lab/lab_greeter",
  "examples/hello_lab/lab_greeter_tests",
]

[suite]
mode = "new"
ready_fn = "lab_greeter_tests.status"
calls = [
  "lab_greeter_tests.in_lab_profile",
  "lab_greeter_tests.message_format",
  "lab_greeter_tests.hook_fired",
  "lab_greeter_tests.player_in_world",
]

[guard]
# Other test folders inside your game profile that this lab should not watch.
ignore_profile_dirs = []
"""


def toml_path(p: Path) -> str:
    return "'" + str(p) + "'"
