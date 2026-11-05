# Testing lessons

These come from building and releasing real mods with this lab. They concern how to test, not how the game works.

## Protect the save before testing

Use a separate copy, a separate profile and a throwaway save. Check the redirect in the running game, and compare your real files before and after. A backup alone does not prove a test was isolated.

## Read what the game does

MOMI's install exposes the game's scripts in your own copy. Follow an operation through its whole life, including close and cleanup callbacks. Keep what you read out of your repo. Ship your own code, which calls the game's functions at runtime.

## Treat a passing result narrowly

Compilation, unit tests, runtime calls and looking at the screen each prove different things. Say which one you ran. A virtual controller exercises the game's gamepad code and says nothing about how a physical controller feels. A 1280x800 window checks the Steam Deck's shape and does not prove the mod works on SteamOS.

## Make a test prove the operation

Require a fresh result from the current process, naming the function you called. Check the thing you care about, such as item quantity and owner, and not a side effect, such as an empty slot. If a test restores state on failure, also prove that the failure happened at the point you meant to test.

Keep product bugs, mistakes in your test setup and tool failures in separate categories when you record results.

## Measure the slow frames

Report the typical and the worst callback time. A low median can hide periodic work. A single 18 ms callback nearly uses up a 60 Hz frame. Test with varied, realistic data, not mostly empty storage.

## Look at the real thing for visual work

Layout checks catch overlaps and text that does not fit. They cannot tell you a screen looks right. Check the smallest supported window, because a bigger window does not always give you more layout space. Let fades and layout settle before taking a screenshot.

## Test the package you ship

Test the extracted zip through install, removal and reinstall, not only the source folder. Line endings count if you compare hashes.

Check PowerShell exit codes straight after each command, because a later success can hide an earlier failure.
