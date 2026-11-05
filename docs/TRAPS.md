# Known traps

Each of these happened during real testing on game 1.0.8 and MOMI 0.17.0. Check them again after an update.

## MOMI has no help flag

The MOMI CLI treats any argument it does not recognize as "install". `--help` starts a full install into your Steam game, and it moves your clean archive to `assets.bak.zip` on the way.

The lab builds every MOMI command itself and refuses unknown arguments. If you run the CLI by hand, the safe commands are `--version` and `--lint <mod folder> <unmodded assets.zip>`.

## MOMI installs into Steam first

MOMI has no option to choose a target folder. It searches a fixed list of Steam locations for `Maybe.toml`, and it uses its working directory only if none is found. So MOMI run from a test folder still installs into Steam, and its success message does not tell you which folder it used.

What the lab does for each install:

1. It refuses to start if MOMI could find a second game copy, because it can protect only one.
2. It renames Steam's `Maybe.toml` to `Maybe.toml.lab-hold` while MOMI runs, then renames it back.
3. It reads MOMI's output and kills MOMI if it reports any folder other than the lab copy.
4. It confirms that the lab's archive was modded and that the Steam folder is unchanged.

If the PC loses power during an install, the hold file stays behind and `install` refuses to run. Run `python lab.py recover` to rename it back. Do not start the real game or let Steam update it while an install is running.

## An old assets.bak.zip

MOMI keeps your clean archive as `assets.bak.zip`. A game update replaces `assets.zip` but leaves that backup, so until MOMI runs again the backup is older than your game. Testing on it means testing the wrong version.

`setup` compares the game's version script in the backup and in the live archive, and it stops if they differ. To get a clean archive, verify the game files in Steam, run `setup`, then run MOMI to put your mods back.

## Game updates wipe mods

A game update replaces `assets.zip`, so every mod silently disappears from the real game. Your lab copy stays on the old version. Delete `work\game` and `work\pristine-assets.zip`, then run `setup` and `install` again.

## Double load crash

`--auto-start continue` loads a save by itself. If a mod or test also starts a load from the title screen, the game starts the load twice, opens a second window, stops logging and never reaches the world.

In a mod that loads saves, stand aside when the option is set, for example with `if (AUTO_START != "off") return;`. In a test, use one method to reach the save.

## `--auto-start continue` fires at every title

The option applies every time the title screen opens, not only at launch. A test that returns to the title reloads a save about a quarter of a second later. Use this on purpose for switching saves, keep only the wanted save in the folder, and do not write a test that expects to stay on the title screen in this mode.

## Returning to the title during the room banner

The game shows the room name when you enter an area. Returning to the title while that banner is running crashed the lab, with no mod code in the stack. Wait about 12 seconds after entering a room before you leave the world.

## Engine logs ignore the save redirect

The redirect moves saves, settings and mod data. The engine still writes `log.txt`, `error_log.json` and `crash-images` to the real profile root, and all game copies share them. This has three effects:

- Two copies running together corrupt each other's logs and timing, so the lab refuses to launch next to any process named `FieldsOfMistria*`, including your real game.
- The lab saves the two real log files at launch and restores them at `stop`.
- `stop` moves this run's logs and crash images to `work\logs\engine-<time>`. Look there after a crash. Always run `stop`.

`error_log.json` is not cleared between runs in the real game. An old entry looks like fresh evidence, so check its timestamp.

## Debug calls start late

MMAPI's debug agent is off unless `mod_data/mmapi/mmapi.json` contains `{"debug_enabled": true}`. The lab writes that file in the lab profile only. Calls run once the game object exists, so a call on a fresh title screen in `--mode menu` waits and then times out.

`game.room_changed` does not fire for the room a session starts in. A test that waits for it must change rooms first.

## Old results look like new results

The agent's `state.json` keeps the last result, and revisions survive restarts. The lab deletes the old state at launch, queues an empty batch to clear stale commands, and requires the answer to name the function that was called. If you write your own client, do the same.

## Dotted paths can lose their receiver

Calling a native method by dotted path did not always keep its object, so setters failed before changing anything. Register a function in your test mod that calls the method on the object, and call that instead.

## Fixtures that a new save does not have

A test written against one save can fail on a new save for reasons unrelated to your mod, such as a first-use message that has already been shown there. Build what you need in the test, or keep a save with `save-fixture` and use `--mode continue`.

A generated item with a valid ID can still lack data the game needs. A cosmetic built from its ID alone crashed when the game drew its icon. Build test items with the game's own factories.

## Mod rules that MOMI enforces

Strict lint requires each top-level function to start with your mod's name, and a mod download must hold one folder with no loose files beside it. Run `python lab.py lint` to check a mod without installing it.
