# Mistria Modding Lab

Test your Fields of Mistria mods without risking your real saves.

The lab builds a separate copy of the game on your PC, installs your mod into that copy with the Mods of Mistria Installer (MOMI), and redirects the copy's saves to their own folder. It starts the game on a hidden Windows desktop with the sound muted, runs test functions inside the running game, and reports pass or fail. Before and after each step it checks that your real saves and your Steam install have not changed.

This is a community tool. It is not made by or affiliated with NPC Studio, MOMI or MMAPI.

## What you need

- Windows 10 or 11
- Fields of Mistria on Steam
- Python 3.11 or newer. The lab uses only the standard library, so there is nothing to `pip install`.
- `ModsOfMistriaInstaller-cli.exe` from the [MOMI releases page](https://github.com/Garethp/Mods-of-Mistria-Installer/releases)
- About 2 GB of free disk space

**Tested on:** game 1.0.8 (Steam build 25915137), MOMI 0.17.0, Windows 11. Other versions may work. If a game update moves the code the lab patches, the lab stops with a message and does not guess.

## Quick start

Open PowerShell in the folder where you want the lab.

```powershell
git clone https://github.com/sturimcode/mistria-modding-lab
cd mistria-modding-lab
python lab.py init --momi "C:\path\to\ModsOfMistriaInstaller-cli.exe"
python lab.py doctor
python lab.py setup
python lab.py install
python lab.py test
```

| Step | What it does |
| --- | --- |
| `init` | Finds your game and writes `lab.toml`, your local settings. It is not committed. |
| `doctor` | Checks your setup and changes nothing. Fix anything marked `FIX`. |
| `setup` | Copies the game into `work\game` and keeps an unmodded copy of the game archive. |
| `install` | Rebuilds the lab copy from the unmodded archive, installs the mods listed in `lab.toml`, and applies the save redirect. |
| `test` | Starts the game, waits for the world, runs the test functions, closes the game and checks your real files. |

The last lines of `test` should look like this:

```text
PASS lab_greeter_tests.in_lab_profile
PASS lab_greeter_tests.message_format
PASS lab_greeter_tests.hook_fired
PASS lab_greeter_tests.player_in_world
4 of 4 passed. Results: ...\work\results\suite-20261105T101500.json
engine logs from this run: ...\work\logs\engine-20261105T101500
guard: real saves and the Steam install are unchanged
```

`install` briefly renames one file in your Steam folder. [The traps page](docs/TRAPS.md#momi-installs-into-steam-first) explains why and what happens if it is interrupted.

## Worked example: the sample mod

[`examples/hello_lab`](examples/hello_lab) holds two small mods. The default `lab.toml` installs both.

**`lab_greeter`** is the mod being tested. It counts how often the title screen opens and builds a message.

```gml
function lab_greeter_message(_visits) {
    return _visits == 1 ? "Welcome to Mistria." : "Welcome back. Visit " + string(_visits) + ".";
}
```

**`lab_greeter_tests`** is a second mod that holds the tests. Install it in the lab only and never ship it. Keeping tests in their own mod means your release folder contains no test code.

A test is a GML function that returns a struct with `passed`. You publish it to the lab with `mmapi_debug_register_fn`:

```gml
function lab_greeter_tests_message_format() {
    lab_greeter_tests_guard();
    var _first = lab_greeter_message(1), _later = lab_greeter_message(3);
    return { passed: _first == "Welcome to Mistria." && _later == "Welcome back. Visit 3.", first: _first, later: _later };
}

function lab_greeter_tests_tick() {
    var _state = lab_greeter_tests_state();
    if (_state.registered || environment_get_variable("MISTRIA_LAB") != "1") return;
    _state.registered = true;
    mmapi_debug_register_fn("lab_greeter_tests.message_format", lab_greeter_tests_message_format, {});
}

mmapi_mod_declare("lab_greeter_tests", "1.0.0");
mmapi_register(lab_greeter_tests_tick);
```

The lab starts the game with the environment variables `MISTRIA_LAB=1` and `MISTRIA_LAB_PROFILE=<profile name>`. `lab_greeter_tests_guard()` refuses to run unless saves really go to that profile, so a test mod copied into a real game does nothing harmful.

`lab.toml` names the functions to run:

```toml
[suite]
mode = "new"
ready_fn = "lab_greeter_tests.status"
calls = [
  "lab_greeter_tests.in_lab_profile",
  "lab_greeter_tests.message_format",
  "lab_greeter_tests.hook_fired",
  "lab_greeter_tests.player_in_world",
]
```

The lab calls `ready_fn` until it returns `active: true`, then runs each entry in `calls`. A call passes only if it raises no error and returns `passed: true`.

To see a failure, change `"Welcome to Mistria."` in `LabGreeter.gml`, then run `python lab.py install` and `python lab.py test`. `message_format` reports `FAIL` with the values it received.

## Test your own mod

1. Copy `examples/hello_lab/lab_greeter_tests` and rename it, its manifest, and its function prefix to match your mod.
2. In `lab.toml`, list your mod folder and your test folder under `[mods]`, and your functions under `[suite]`.
3. Run `python lab.py install`, then `python lab.py test`.

To try things by hand with the game still running:

```powershell
python lab.py launch --mode new
python lab.py call lab_greeter_tests.status
python lab.py call lab_greeter_tests.message_format
python lab.py stop
```

Always finish with `stop`. It closes the game, puts the real engine logs back and runs the check of your real files.

## Commands

| Command | What it does |
| --- | --- |
| `init` | Write `lab.toml` |
| `doctor` | Check the setup and change nothing |
| `setup` | Build the separate game copy |
| `lint [mods]` | Ask MOMI whether a mod would install, and change nothing |
| `install [mods]` | Rebuild the copy with these mods |
| `sync <mod>` | Copy changed `.gml` files into the copy, which is faster than `install`. New files need `install`. |
| `launch --mode new\|continue\|menu --window hidden\|offscreen\|visible` | Start the lab game |
| `call <fn> --args "[1,2]"` | Run one registered function. `--path` resolves a dotted path instead. |
| `suite [fns]` | Run the suite in the running game |
| `test` | Launch, run the suite, stop |
| `stop` | Close the game, restore engine logs, check real files |
| `recover` | Finish after a crash or power cut |
| `check` | Compare real files with the state recorded at the last launch |
| `reset-profile` | Delete the lab's saves and settings |
| `save-fixture <name>`, `restore-fixture <name>` | Keep and restore a copy of the lab's saves |

## Settings in `lab.toml`

| Setting | Use |
| --- | --- |
| `[mods] folders` | Mods to install, as paths relative to `lab.toml` or absolute |
| `[lab] window` | `hidden` uses a separate Windows desktop. `offscreen` moves the window out of view, which you may need for tools that read the screen. `visible` is for watching or playing by hand. |
| `[lab] profile_name` | Lab save folder inside `%LOCALAPPDATA%\FieldsOfMistria`. Give each lab its own name. |
| `[lab] exe_name` | Process name of the lab copy |
| `[lab] env` | Extra environment variables for your tests |
| `[settings]` | Game settings to force in the lab, such as `language = "jpn"`. The lab mutes audio, turns off analytics and uses a 1280x720 window by default. |
| `[guard] ignore_profile_dirs` | Other test folders in your profile that the lab should not watch, such as `["my-other-lab*"]` |
| `[[patches]]` | Lab-only edits to game scripts, as `file`, `find` and `replace`. `find` must match exactly once. Use them for timing probes. They never reach your real game. |

You can run several labs side by side on disk with `python lab.py --config other.toml ...`, each with its own `work` folder and `profile_name`. Only one can run at a time, because every copy writes the same engine log.

## Safety

What protects your game, and what does not:

- **Separate copy.** Mods go into `work\game`, not Steam.
- **Redirected saves.** The lab patches its own archive so saves, settings and mod data go to `%LOCALAPPDATA%\FieldsOfMistria\<profile_name>`. The lab refuses to launch if the patch is missing.
- **Real-file guard.** The lab fingerprints your real profile and Steam folder and compares them after each step. Profile files are hashed in full. Steam files are compared by size and modified time.
- **Quiet and out of the way.** The game runs on a hidden desktop with audio at zero.
- **Deletes only its own folders.** The lab deletes only inside folders it marked as its own.

Limits you should know:

- `install` renames Steam's `Maybe.toml` while MOMI runs.
- Engine logs and crash images are written to your real profile while the lab runs. The lab moves them to `work\logs` and restores the originals.
- The guard detects changes and does not undo them. Keep your own backup of saves you care about.
- A test mod can do anything GML can do, so read test mods before you run them.

Read [docs/TRAPS.md](docs/TRAPS.md) before you write your own tests. Each trap there cost a real test run.

## What the lab does not prove

Passing tests show that your functions returned what you expected in a running game. They do not show how your mod looks, how a controller feels, or how it behaves on Steam Deck. For anything visual, launch with `--window visible` and look.

The lab has no menu navigation or input tools, and it runs on Windows only. Debug calls start once the game object exists, so they do not run on the first title screen.

## Further reading

- [docs/TRAPS.md](docs/TRAPS.md): known traps and what to do about them
- [docs/LESSONS.md](docs/LESSONS.md): testing lessons from building real mods
- [MMAPI debug agent](https://github.com/Garethp/Mods-of-Mistria-Installer/blob/main/docs/MMAPI/DEBUG.md): the bridge the lab uses to call functions
- [MMAPI quick start](https://github.com/Garethp/Mods-of-Mistria-Installer/blob/main/docs/MMAPI/QUICK_START.md): writing your first GML mod

## License and game content

The code and sample mods here are under the [MIT License](LICENSE).

This repo contains no game files, game scripts, saves or MOMI binaries. The lab copies files from your own install, on your own PC, and they stay there. Do not commit or share the `work` folder. It contains the game. Your use of the game remains subject to [NPC Studio's EULA](https://fieldsofmistria.com/eula), which you should read yourself. MOMI and MMAPI are separate projects under their own licenses (GPL-3.0, with additional terms for MMAPI).

Fields of Mistria is a trademark of its owner. The names here only describe what this tool works with.
