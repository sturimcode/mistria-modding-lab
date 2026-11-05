"""Tests that need no game. Run: python -m unittest discover -s tests"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mistria_lab import config, guard, lab as lab_module, momi
from mistria_lab.config import Config, LabStop


class TempLab(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.install = self.root / 'steam' / 'Fields of Mistria'
        self.install.mkdir(parents=True)
        (self.install / 'Maybe.toml').write_text('name = "game"')
        self.profile = self.root / 'profile'
        (self.profile / 'saves').mkdir(parents=True)
        (self.profile / 'saves' / 'real.sav').write_text('real save')
        (self.profile / 'log.txt').write_text('real log')
        self.cfg = Config(path=self.root / 'lab.toml', install_dir=self.install, profile_root=self.profile,
                          momi_cli=self.root / 'momi.exe', work=self.root / 'work')
        self.cfg.work.mkdir()
        self.cfg.game.mkdir()
        (self.cfg.game / lab_module.MARKER).write_text('x')
        self.lab = lab_module.Lab(self.cfg)

    def make_archive(self, path, modded=False, anchor=lab_module.SAVE_ANCHOR):
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr(lab_module.SAVE_ROUTE, f'function f() {{\n    {anchor}\n}}\n')
            z.writestr(lab_module.VERSION_FILE, 'version')
            if modded:
                z.writestr(momi.MODDED_MARKER, 'x')


class SafeArgs(unittest.TestCase):
    def test_help_never_reaches_momi(self):
        for bad in (['--help'], ['-h'], ['/?'], []):
            with self.assertRaises(LabStop):
                momi.safe_args(bad)
            if bad:
                with self.assertRaises(LabStop):
                    momi.safe_args(bad, installing=True)

    def test_known_commands_pass(self):
        self.assertEqual(momi.safe_args(['--version']), ['--version'])
        lint = ['--lint', 'mod', 'zip', '--strict-lints', '--compile-check', 'require']
        self.assertEqual(momi.safe_args(lint), lint)

    def test_lint_needs_an_archive(self):
        with self.assertRaises(LabStop):
            momi.safe_args(['--lint', 'mod'])

    def test_uninstall_refused(self):
        with self.assertRaises(LabStop):
            momi.safe_args(['--uninstall'], installing=True)

    def test_install_flags(self):
        flags = ['--strict-lints', '--fail-on-skip', '--compile-check', 'require']
        self.assertEqual(momi.safe_args(flags, installing=True), flags)


class ConfigChecks(TempLab):
    def test_profile_names(self):
        for bad in ('saves', 'mods', 'a/b', '..', 'x"; evil', 'UPPER', ''):
            self.cfg.profile_name = bad
            with self.assertRaises(LabStop, msg=bad):
                config.validate(self.cfg)

    def test_work_folder_cannot_be_in_steam_or_profile(self):
        for bad in (self.install / 'lab', self.profile / 'lab'):
            self.cfg.work = bad
            with self.assertRaises(LabStop):
                config.validate(self.cfg)

    def test_launch_args_cannot_carry_auto_start(self):
        self.cfg.launch_args = ['--auto-start=new']
        with self.assertRaises(LabStop):
            config.validate(self.cfg)

    def test_template_parses(self):
        path = self.root / 'written.toml'
        path.write_text(config.TEMPLATE.format(install=config.toml_path(self.install), momi=config.toml_path(self.root / 'm.exe')))
        cfg = config.load(path)
        self.assertEqual(cfg.install_dir, self.install)
        self.assertEqual(cfg.window, 'hidden')
        self.assertTrue(cfg.suite.calls)


class Guard(TempLab):
    def test_detects_changed_save(self):
        before = guard.snapshot(self.cfg)
        (self.profile / 'saves' / 'real.sav').write_text('changed')
        with self.assertRaises(LabStop):
            guard.require_unchanged(before, self.cfg)

    def test_detects_added_and_removed_files(self):
        before = guard.snapshot(self.cfg)
        (self.profile / 'saves' / 'new.sav').write_text('new')
        self.assertEqual(guard.differences(before, guard.snapshot(self.cfg)), ['profile/saves/new.sav'])
        (self.profile / 'saves' / 'new.sav').unlink()
        (self.profile / 'saves' / 'real.sav').unlink()
        self.assertEqual(guard.differences(before, guard.snapshot(self.cfg)), ['profile/saves/real.sav'])

    def test_detects_steam_change(self):
        before = guard.snapshot(self.cfg)
        (self.install / 'assets.zip').write_text('x')
        with self.assertRaises(LabStop):
            guard.require_unchanged(before, self.cfg)

    def test_engine_log_ignored_only_when_asked(self):
        before = guard.snapshot(self.cfg)
        (self.profile / 'log.txt').write_text('game wrote this')
        guard.require_unchanged(before, self.cfg, skip_engine=True)
        with self.assertRaises(LabStop):
            guard.require_unchanged(before, self.cfg)

    def test_lab_and_ignored_profiles_skipped(self):
        self.cfg.ignore_profile_dirs = ['other-*']
        before = guard.snapshot(self.cfg)
        for name in (self.cfg.profile_name, 'other-lab'):
            (self.profile / name).mkdir()
            (self.profile / name / 'f').write_text('x')
        guard.require_unchanged(before, self.cfg)


class Redirect(TempLab):
    def test_applies_once_and_verifies(self):
        self.make_archive(self.cfg.game / 'assets.zip')
        self.lab.apply_archive_edits()
        self.lab.verify_redirect()
        with zipfile.ZipFile(self.cfg.game / 'assets.zip') as z:
            self.assertIn('/mistria-lab', z.read(lab_module.SAVE_ROUTE).decode())

    def test_unpatched_archive_refused(self):
        self.make_archive(self.cfg.game / 'assets.zip')
        with self.assertRaises(LabStop):
            self.lab.verify_redirect()

    def test_moved_anchor_stops(self):
        self.make_archive(self.cfg.game / 'assets.zip', anchor='return something_else;')
        with self.assertRaises(LabStop):
            self.lab.apply_archive_edits()

    def test_extra_patch(self):
        self.make_archive(self.cfg.game / 'assets.zip')
        self.cfg.patches = [{'file': lab_module.VERSION_FILE, 'find': 'version', 'replace': 'probe'}]
        self.lab.apply_archive_edits()
        with zipfile.ZipFile(self.cfg.game / 'assets.zip') as z:
            self.assertEqual(z.read(lab_module.VERSION_FILE), b'probe')


class Pristine(TempLab):
    def test_unmodded_live_archive_chosen(self):
        self.make_archive(self.install / 'assets.zip')
        self.assertEqual(self.lab.choose_pristine(), self.install / 'assets.zip')

    def test_backup_used_when_live_is_modded(self):
        self.make_archive(self.install / 'assets.zip', modded=True)
        self.make_archive(self.install / 'assets.bak.zip')
        self.assertEqual(self.lab.choose_pristine(), self.install / 'assets.bak.zip')

    def test_old_backup_refused(self):
        self.make_archive(self.install / 'assets.zip', modded=True)
        with zipfile.ZipFile(self.install / 'assets.bak.zip', 'w') as z:
            z.writestr(lab_module.VERSION_FILE, 'older')
        with self.assertRaises(LabStop):
            self.lab.choose_pristine()

    def test_modded_without_backup_refused(self):
        self.make_archive(self.install / 'assets.zip', modded=True)
        with self.assertRaises(LabStop):
            self.lab.choose_pristine()


class Deletion(TempLab):
    def test_reset_refuses_unmarked_folder(self):
        self.cfg.profile.mkdir()
        (self.cfg.profile / 'keep.sav').write_text('x')
        with mock.patch.object(lab_module.winapi, 'game_processes', return_value=[]), self.assertRaises(LabStop):
            self.lab.reset_profile()
        self.assertTrue((self.cfg.profile / 'keep.sav').exists())

    def test_reset_deletes_marked_folder(self):
        self.cfg.profile.mkdir()
        (self.cfg.profile / lab_module.MARKER).write_text('x')
        with mock.patch.object(lab_module.winapi, 'game_processes', return_value=[]):
            self.lab.reset_profile()
        self.assertFalse(self.cfg.profile.exists())
        self.assertTrue((self.profile / 'saves' / 'real.sav').exists())


class EngineFiles(TempLab):
    def test_logs_restored_and_new_crash_images_moved(self):
        hold = self.lab.hold
        hold.mkdir()
        shutil.copy2(self.profile / 'log.txt', hold / 'log.txt')
        (self.profile / 'crash-images').mkdir()
        (self.profile / 'crash-images' / 'old.png').write_text('old')
        (self.cfg.work / 'session-baseline.json').write_text(json.dumps(guard.snapshot(self.cfg)))
        (self.profile / 'log.txt').write_text('lab log')
        (self.profile / 'error_log.json').write_text('lab error')
        (self.profile / 'crash-images' / 'new.png').write_text('new')
        self.lab.restore_engine_files()
        self.assertEqual((self.profile / 'log.txt').read_text(), 'real log')
        self.assertFalse((self.profile / 'error_log.json').exists())
        self.assertTrue((self.profile / 'crash-images' / 'old.png').exists())
        self.assertFalse((self.profile / 'crash-images' / 'new.png').exists())
        kept = list(self.cfg.logs.glob('engine-*'))[0]
        self.assertEqual((kept / 'log.txt').read_text(), 'lab log')
        self.assertTrue((kept / 'crash-images' / 'new.png').exists())


class FakeMomi:
    def __init__(self, lines, code=0):
        self.stdout = io.StringIO(''.join(line + '\n' for line in lines))
        self.returncode = code
        self.killed = False

    def kill(self):
        self.killed = True

    def wait(self):
        return self.returncode


class InstallRun(TempLab):
    def run_install(self, lines, code=0, on_run=None, found=None):
        found = [self.install] if found is None else found
        fake = FakeMomi(lines, code)

        def popen(*args, **kwargs):
            if on_run:
                on_run()
            return fake

        with mock.patch.object(momi, 'momi_running', return_value=False), \
                mock.patch.object(momi, 'momi_search_locations', return_value=found), \
                mock.patch.object(momi.subprocess, 'Popen', side_effect=popen):
            momi.run_install(self.cfg, self.cfg.logs / 'x.log')
        return fake

    def test_maybe_hidden_during_run_and_restored(self):
        seen = []
        self.make_archive(self.cfg.game / 'assets.zip', modded=True)
        self.run_install(['ok'], on_run=lambda: seen.append((self.install / 'Maybe.toml').exists()))
        self.assertEqual(seen, [False])
        self.assertTrue((self.install / 'Maybe.toml').exists())
        self.assertFalse((self.install / momi.HOLD).exists())

    def test_wrong_target_killed_and_restored(self):
        self.make_archive(self.cfg.game / 'assets.zip', modded=True)
        with self.assertRaises(LabStop):
            self.run_install([f'Guessed Location: {self.install}'])
        self.assertTrue((self.install / 'Maybe.toml').exists())

    def test_failure_exit_stops_and_restores(self):
        self.make_archive(self.cfg.game / 'assets.zip', modded=True)
        with self.assertRaises(LabStop):
            self.run_install(['bad'], code=1)
        self.assertTrue((self.install / 'Maybe.toml').exists())

    def test_silent_success_without_modded_archive_stops(self):
        self.make_archive(self.cfg.game / 'assets.zip', modded=False)
        with self.assertRaises(LabStop):
            self.run_install(['Could not find anything'])

    def test_second_game_copy_refused_before_anything_moves(self):
        other = self.root / 'other'
        other.mkdir()
        (other / 'Maybe.toml').write_text('x')
        with self.assertRaises(LabStop):
            self.run_install(['ok'], found=[self.install, other])
        self.assertTrue((self.install / 'Maybe.toml').exists())

    def test_stale_hold_stops_then_recover_restores(self):
        os.replace(self.install / 'Maybe.toml', self.install / momi.HOLD)
        with self.assertRaises(LabStop):
            self.run_install(['ok'])
        with mock.patch.object(momi, 'momi_running', return_value=False):
            self.assertTrue(momi.recover(self.cfg))
        self.assertTrue((self.install / 'Maybe.toml').exists())

    def test_recover_refuses_when_both_exist(self):
        (self.install / momi.HOLD).write_text('x')
        with mock.patch.object(momi, 'momi_running', return_value=False), self.assertRaises(LabStop):
            momi.recover(self.cfg)


class SampleMod(unittest.TestCase):
    def test_tests_mod_registers_only_in_lab(self):
        root = Path(__file__).resolve().parents[1] / 'examples' / 'hello_lab'
        source = (root / 'lab_greeter_tests' / 'gml' / 'LabGreeterTests.gml').read_text()
        self.assertIn('environment_get_variable("MISTRIA_LAB") != "1"', source)
        shipped = (root / 'lab_greeter' / 'gml' / 'LabGreeter.gml').read_text()
        self.assertNotIn('mmapi_debug_register_fn', shipped)


if __name__ == '__main__':
    unittest.main()
