# Public release checklist

Results for the first public release, version 0.1.0, on 5 November 2026. Tested on game 1.0.8 (Steam build 25915137), MOMI 0.17.0 and Windows 11.

## Works for any mod

| Check | Result |
| --- | --- |
| Paths, mod names, profile, exe name and suite come from `lab.toml` | Pass |
| No Tidy Chests or other mod name in the code | Pass: scanner found none |
| Lab-only game patches are available as config, without code changes | Pass: `[[patches]]`, unit tested |

## Safety features

| Check | Result |
| --- | --- |
| Separate game copy | Pass: installed into `work\game` |
| Redirected saves | Pass: a save made in the lab landed in the lab profile |
| Refuses to launch without the redirect | Pass: unit tested |
| Real-file guard over saves and the Steam install | Pass: reported unchanged on every step |
| Independent check, written apart from the guard | Pass: 554 real files hashed before and after all runs, 0 differences |
| Muted, and hidden or off-screen | Pass: hidden and off-screen both ran. Muting is set in settings, not measured from audio output. |
| Refuses to run beside another game process | Pass: `doctor` flagged another lab's running game. `launch` calls the same process check, but no launch was attempted beside it. |
| Unknown MOMI arguments refused | Pass: unit tested, including `--help` |
| Stops if MOMI could find a second game copy, or picks the wrong folder | Pass: unit tested with a stand-in for MOMI, not with a real second copy |
| Deletes only folders it marked as its own | Pass: unit tested |
| `recover` after an interrupted install | Pass: unit tested. A real power cut was not simulated. |

## Traps documented

| Check | Result |
| --- | --- |
| Double load crash, return to title during the room banner, MOMI having no help flag | Pass: `docs/TRAPS.md` |
| Others found in testing, including shared engine logs and old backups | Pass: `docs/TRAPS.md` |

## Private and proprietary material

| Check | Result |
| --- | --- |
| No game scripts, assets, `assets.zip`, saves or binaries | Pass: scanner over the working tree and full git history |
| No line of 40 or more characters matches the game's scripts | Pass: compared with 27,190 lines of game script |
| No personal paths, personal email or tokens | Pass |
| Commit identity uses the GitHub no-reply address | Pass |
| Short game strings in the code | Accepted: one script path, one 3-token anchor for the patch, and the names of game functions that the sample tests call |
| MOMI and MMAPI text | Accepted: behavior is described in our own words, with links to their docs |

## README and license

| Check | Result |
| --- | --- |
| What it is, requirements, quick start, worked example, limits | Pass |
| License chosen and stated | Pass: MIT |
| Not presented as affiliated with NPC Studio, MOMI or MMAPI | Pass |
| Redistributes no MOMI code | Pass: the user downloads MOMI |

## README followed as a stranger

Each run used a fresh `git clone` and a fresh work folder, and followed the README's commands.

| Step | Result |
| --- | --- |
| `init`, `doctor`, `setup` | Pass: chose the clean backup archive by itself, and its hash matched the known 1.0.8 archive |
| `install` | Pass: strict lint and required compile succeeded, and `Maybe.toml` was back afterwards |
| `test` | Pass: 4 of 4 in about 20 seconds |
| Failure demo | Pass: 2 of 4 failed as the README says, with exit code 1 |
| `lint`, `sync`, by-hand `launch`, `call`, `stop` | Pass |
| Test on a save: make a save, `save-fixture`, `--mode continue`, `restore-fixture` | Pass: the same save ID came back |
| `reset-profile` | Pass |

Found during this run and fixed: on a hidden desktop, a plain `launch` let the game die during startup.

## Not tested

- A second PC. All runs used one PC where the game was already modded, so the path for an unmodded game is unit tested only.
- A PC that has never run the game, or a Steam library outside the default locations.
- Windows in another language. MOMI's output may be translated, so the check of the lab's own archive is the proof that the install reached the lab.
- Windows 10.
- Steam closed. Steam was running in every test.

## Terms

| Source | Finding |
| --- | --- |
| [NPC Studio EULA](https://fieldsofmistria.com/eula), last updated 31 May 2024 | Does not mention mods. It bars reverse engineering, derivative works and copies beyond what it or the law permits. No official mod policy was found. |
| [MOMI](https://github.com/Garethp/Mods-of-Mistria-Installer) | GPL-3.0. This repo does not redistribute it. |
| MMAPI | GPL-3.0 with additional terms on attribution and on not implying endorsement. This repo includes no MMAPI code and calls its functions only from the sample mods. |
