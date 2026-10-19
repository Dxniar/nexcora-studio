import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from orderbot import config


class ConfigFileTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        package = self.root / 'orderbot'
        package.mkdir()
        (package / '__init__.py').touch()
        shutil.copyfile(config.__file__, package / 'config.py')
        (package / '__main__.py').write_text(
            'import json\nfrom .config import load_config\n'
            'print(json.dumps({"token": load_config().bot_token}))\n',
            encoding='utf-8',
        )
        self.env_path = self.root / '.env'
        self.env_path.write_text('BOT_TOKEN=123456:file_token\n', encoding='utf-8')

    def read_config(self, process_token=None):
        environment = os.environ.copy()
        for key in ('BOT_TOKEN', 'ADMIN_ID', 'OWNER_USERNAME', 'DB_PATH',
                    'PYTHONPATH', 'PYTHON_DOTENV_DISABLED'):
            environment.pop(key, None)
        if process_token is not None:
            environment['BOT_TOKEN'] = process_token
        environment['PYTHONUTF8'] = '1'
        result = subprocess.run(
            [sys.executable, '-m', 'orderbot'],
            cwd=self.root, env=environment, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)['token']

    def test_empty_environment_token_uses_file(self):
        self.assertEqual(self.read_config(''), '123456:file_token')

    def test_placeholder_environment_token_uses_file(self):
        self.assertEqual(self.read_config('put_your_bot_token_here'), '123456:file_token')

    def test_configured_environment_token_takes_priority(self):
        self.assertEqual(self.read_config('654321:environment_token'),
                         '654321:environment_token')

    def test_root_env_takes_priority_over_nested_env(self):
        (self.root / 'orderbot' / '.env').write_text(
            'BOT_TOKEN=put_your_bot_token_here\n', encoding='utf-8',
        )
        self.assertEqual(self.read_config(), '123456:file_token')


if __name__ == '__main__':
    unittest.main()
