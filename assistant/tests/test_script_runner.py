import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ScriptRunnerTests(unittest.TestCase):
    def installation(self, root, label):
        (root / 'scripts').mkdir(parents=True)
        (root / '.codex-plugin').mkdir()
        (root / '.codex-plugin/plugin.json').write_text('{"name":"assistant"}')
        shutil.copyfile(ROOT / 'scripts/run-script.py', root / 'scripts/run-script.py')
        (root / 'scripts/vault-health.py').write_text(
            'import os,json,sys\nprint(json.dumps({"root":os.environ["ASSISTANT_PLUGIN_ROOT"],'
            f'"label":{label!r},"args":sys.argv[1:],"cwd":os.getcwd()}}))\n')
        return root / 'scripts/run-script.py'

    def run_script(self, runner, args, root=None):
        env = dict(os.environ)
        for name in ['ASSISTANT_PLUGIN_ROOT', 'CLAUDE_PLUGIN_ROOT', 'CLAUDECODE']:
            env.pop(name, None)
        if root is not None:
            env['ASSISTANT_PLUGIN_ROOT'] = str(root)
        return subprocess.run([sys.executable, str(runner), *args], env=env, capture_output=True, text=True)

    def test_relocated_runner_without_env_or_hook_preserves_args_and_cwd(self):
        with tempfile.TemporaryDirectory(prefix='assistant space ') as tmp:
            root = Path(tmp) / 'cache with spaces'
            runner = self.installation(root, 'relocated')
            result = self.run_script(runner, ['vault-health.py', '--nudge'])
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(Path(data['root']), root.resolve())
            self.assertEqual(data['args'], ['--nudge'])
            self.assertEqual(data['cwd'], os.getcwd())

    def test_explicit_root_wins_and_invalid_root_fails_without_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = self.installation(root / 'one', 'one')
            self.installation(root / 'two', 'two')
            result = self.run_script(runner, ['vault-health.py'], root / 'two')
            self.assertEqual(json.loads(result.stdout)['label'], 'two')
            result = self.run_script(runner, ['vault-health.py'], root / 'missing')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(str(root / 'missing'), result.stderr)
            self.assertNotIn("can't open file '/scripts", result.stderr)

    def test_default_cli_collects_both_hosts_even_when_env_requests_claude(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = [sys.executable, str(ROOT / 'scripts/analyze-activity.py'), '2026-09-08',
                    '--claude-home', tmp, '--codex-home', tmp, '--vault', tmp, '--json-only']
            env = dict(os.environ, ASSISTANT_HOST='claude')
            result = subprocess.run(args, capture_output=True, text=True, env=env, check=True)
            data = json.loads(result.stdout)
            self.assertEqual(data['hosts'], ['claude', 'codex'])
            self.assertEqual(set(data['source_health']), {'claude', 'codex'})
            result = subprocess.run(args + ['--host', 'auto'], capture_output=True, text=True, env=env, check=True)
            self.assertEqual(json.loads(result.stdout)['hosts'], ['claude'])
