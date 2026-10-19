"""Run untrusted document parsing in a bounded, short-lived child process."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from .errors import DomainError
from .runtime import blocking

_gate = asyncio.Semaphore(1)


async def validate_file(path: Path, extension: str) -> str:
    def run():
        environment = {key: os.environ[key] for key in ('SystemRoot', 'WINDIR', 'TEMP', 'TMP', 'PATH', 'LANG') if key in os.environ}
        environment['PYTHONUTF8'] = '1'
        return subprocess.run([sys.executable, '-m', 'nexcora_studio.validation_worker', str(path.resolve()), extension],
                              cwd=Path(__file__).resolve().parent.parent, env=environment,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=12,
                              creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
    try:
        async with _gate:
            result = await blocking(run)
        if result.returncode != 0 or len(result.stdout) > 4096:
            raise ValueError('unverifiable file')
        value = json.loads(result.stdout)
        if not value.get('ok') or not isinstance(value.get('mime'), str): raise ValueError('invalid validation response')
        return value['mime']
    except (ValueError, OSError, subprocess.TimeoutExpired):
        raise DomainError('file_format_rejected', 'Файл не прошёл проверку формата. Для TXT используйте UTF-8; документы должны открываться без пароля.', 415) from None
