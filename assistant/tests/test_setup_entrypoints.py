import importlib.util
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/setup-entrypoints.py'
spec = importlib.util.spec_from_file_location('setup_entrypoints', SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def state(vault):
    return {p.name: module.snapshot(p) for p in vault.iterdir()}


class SetupEntrypointsTests(unittest.TestCase):
    def test_fresh_setup_and_repeat_are_identical_in_both_host_environments(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshots = []
            for host in ['claude', 'codex']:
                vault = Path(tmp) / host
                vault.mkdir()
                environment = {'HOME': str(Path(tmp) / 'empty-home'), 'ASSISTANT_HOST': host}
                if host == 'claude':
                    environment['CLAUDECODE'] = '1'
                with patch.dict(os.environ, environment, clear=True):
                    result = module.run(vault, write=True)
                    self.assertEqual(result['status'], 'updated')
                    original = state(vault)
                    inode = (vault / 'AGENTS.md').stat().st_ino
                    self.assertEqual(module.run(vault, write=True)['status'], 'ok')
                    self.assertEqual(original, state(vault))
                    self.assertEqual(inode, (vault / 'AGENTS.md').stat().st_ino)
                self.assertEqual(os.readlink(vault / 'CLAUDE.md'), 'AGENTS.md')
                self.assertEqual((vault / 'AGENTS.md').read_bytes(), (vault / 'CLAUDE.md').read_bytes())
                snapshots.append(original)
            self.assertEqual(snapshots[0], snapshots[1])

    def test_check_is_read_only_and_runner_can_apply(self):
        with tempfile.TemporaryDirectory(prefix='vault space ') as tmp:
            vault = Path(tmp)
            args = [sys.executable, str(ROOT / 'scripts/run-script.py'), 'setup-entrypoints.py', '--vault', tmp]
            env = dict(os.environ)
            env.pop('ASSISTANT_PLUGIN_ROOT', None)
            result = subprocess.run(args + ['--check'], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(state(vault), {})
            result = subprocess.run(args + ['--apply'], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run(args, capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_custom_bytes_and_file_permissions_survive_block_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            prefix = '# 用户规则\r\n\r\n不自动推送。\r\n'.encode()
            suffix = '\r\n\r\n## 自定义\r\n<!-- 保留注释 -->\r\n'.encode()
            (vault / 'AGENTS.md').write_bytes(prefix + module.BEGIN + b'\nold\n' + module.END + suffix)
            (vault / 'AGENTS.md').chmod(0o600)
            module.run(vault, write=True)
            contents = (vault / 'AGENTS.md').read_bytes()
            self.assertTrue(contents.startswith(prefix))
            self.assertTrue(contents.endswith(suffix))
            self.assertEqual((vault / 'AGENTS.md').stat().st_mode & 0o777, 0o600)
            self.assertNotIn(b'\nold\n', contents)
            self.assertEqual(contents.count(module.BEGIN), 1)

    def test_unmarked_agents_content_is_retained_verbatim(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            original = b'# My rules\n\nUser paragraph without trailing newline'
            (vault / 'AGENTS.md').write_bytes(original)
            module.run(vault, write=True)
            self.assertTrue((vault / 'AGENTS.md').read_bytes().startswith(original + b'\n\n'))

    def test_claude_only_is_adopted_without_losing_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            original = b'# User rules\nDo not deploy\n'
            (vault / 'CLAUDE.md').write_bytes(original)
            module.run(vault, write=True)
            self.assertTrue((vault / 'AGENTS.md').read_bytes().startswith(original))
            self.assertTrue((vault / 'CLAUDE.md').is_symlink())

    def test_equal_files_and_import_stub_can_become_links(self):
        for claude in [b'# User rules\n', b'@AGENTS.md\n', b'']:
            with self.subTest(claude=claude), tempfile.TemporaryDirectory() as tmp:
                vault = Path(tmp)
                (vault / 'AGENTS.md').write_bytes(b'# User rules\n')
                (vault / 'CLAUDE.md').write_bytes(claude)
                module.run(vault, write=True)
                self.assertEqual(os.readlink(vault / 'CLAUDE.md'), 'AGENTS.md')

    def test_independent_content_requires_review_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / 'AGENTS.md').write_text('Shared rules\n')
            (vault / 'CLAUDE.md').write_text('Distinct local rules\n')
            before = state(vault)
            with self.assertRaises(module.Conflict):
                module.run(vault, write=True)
            self.assertEqual(before, state(vault))

    def test_invalid_markers_are_rejected_before_link_creation(self):
        for value in [module.BEGIN, module.END, module.END + module.BEGIN,
                      module.BEGIN + module.BEGIN + module.END,
                      b'Example: ' + module.BEGIN + b' text ' + module.END,
                      b'```html\n' + module.BEGIN + b'\nexample\n' + module.END + b'\n```']:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                vault = Path(tmp)
                (vault / 'AGENTS.md').write_bytes(value)
                before = state(vault)
                with self.assertRaises(module.Conflict):
                    module.run(vault, write=True)
                self.assertEqual(before, state(vault))

    def test_wrong_links_and_external_agents_are_not_followed_or_replaced(self):
        for filename in ['AGENTS.md', 'CLAUDE.md']:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as tmp:
                parent = Path(tmp)
                vault = parent / 'vault'
                vault.mkdir()
                outside = parent / 'private.md'
                outside.write_text('Do not modify')
                (vault / filename).symlink_to(outside)
                before = state(vault)
                with self.assertRaises(module.Conflict):
                    module.run(vault, write=True)
                self.assertEqual(before, state(vault))
                self.assertEqual(outside.read_text(), 'Do not modify')

    def test_canonical_dangling_link_is_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / 'CLAUDE.md').symlink_to('AGENTS.md')
            module.run(vault, write=True)
            self.assertTrue((vault / 'CLAUDE.md').is_file())
            self.assertEqual(os.readlink(vault / 'CLAUDE.md'), 'AGENTS.md')

    def test_override_and_self_references_require_review(self):
        for filename, contents in [('AGENTS.override.md', 'Override'),
                                   ('AGENTS.md', '1. 读 `CLAUDE.md`\n'),
                                   ('AGENTS.md', 'Read CLAUDE.md\n'),
                                   ('CLAUDE.md', '@AGENTS.md\n## Additional rules')]:
            with self.subTest(contents=contents), tempfile.TemporaryDirectory() as tmp:
                vault = Path(tmp)
                (vault / filename).write_text(contents)
                before = state(vault)
                with self.assertRaises(module.Conflict):
                    module.run(vault, write=True)
                self.assertEqual(before, state(vault))

    def test_unsupported_symlink_does_not_leave_partial_instructions(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            with patch.object(Path, 'symlink_to', side_effect=PermissionError('unsupported')):
                with self.assertRaises(PermissionError):
                    module.run(vault, write=True)
            self.assertEqual(state(vault), {})

    def test_second_replace_failure_rolls_back_first_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / 'AGENTS.md').write_text('Keep exactly\n')
            before = state(vault)
            replace = os.replace
            def fail_link(source, dest):
                if Path(dest).name == 'CLAUDE.md':
                    raise OSError('simulated replacement failure')
                return replace(source, dest)
            with patch.object(module.os, 'replace', side_effect=fail_link):
                with self.assertRaises(OSError):
                    module.run(vault, write=True)
            self.assertEqual(before, state(vault))

    def test_concurrent_change_after_planning_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            before, desired, changes = module.plan(vault)
            (vault / 'AGENTS.md').write_text('Concurrent user content')
            with self.assertRaises(module.Conflict):
                module.apply(vault, before, desired, changes)
            self.assertEqual((vault / 'AGENTS.md').read_text(), 'Concurrent user content')
            self.assertFalse((vault / 'CLAUDE.md').exists())


    def test_relocated_plugin_resolves_its_bundled_template(self):
        with tempfile.TemporaryDirectory(prefix='plugin space ') as tmp:
            root = Path(tmp) / 'installed plugin'
            vault = Path(tmp) / 'vault'
            vault.mkdir()
            (root / 'scripts').mkdir(parents=True)
            (root / 'templates').mkdir()
            (root / '.codex-plugin').mkdir()
            (root / '.codex-plugin/plugin.json').write_text('{"name":"assistant"}')
            for name in ['run-script.py', 'setup-entrypoints.py']:
                shutil.copyfile(ROOT / 'scripts' / name, root / 'scripts' / name)
            shutil.copyfile(ROOT / 'templates/AGENTS.md', root / 'templates/AGENTS.md')
            env = dict(os.environ)
            env.pop('ASSISTANT_PLUGIN_ROOT', None)
            subprocess.run([sys.executable, str(root / 'scripts/run-script.py'), 'setup-entrypoints.py', '--apply'], cwd=vault, env=env, check=True, capture_output=True)
            self.assertTrue((vault / 'CLAUDE.md').is_symlink())
            self.assertIn((root / 'templates/AGENTS.md').read_bytes().strip(), (vault / 'AGENTS.md').read_bytes())
