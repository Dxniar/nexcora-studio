"""Exercise the real S3 HTTP adapter against a loopback fault server."""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from botocore.exceptions import ClientError
from nexcora_studio.settings import Settings
from nexcora_studio.storage import S3Storage


class StorageWireTests(unittest.IsolatedAsyncioTestCase):
    async def test_ambiguous_put_is_sent_once_without_hidden_sdk_retries(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_PUT(self):
                requests.append(self.rfile.read(int(self.headers['Content-Length'])))
                payload = b'<Error><Code>ServiceUnavailable</Code><Message>synthetic</Message></Error>'
                self.send_response(503)
                self.send_header('Content-Length', str(len(payload)))
                self.send_header('Connection', 'close')
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        settings = Settings(bot_token='123:synthetic', admin_id=999,
            database_url='sqlite+aiosqlite:///:memory:', app_origin='http://localhost', development=True,
            s3_endpoint=f'http://127.0.0.1:{server.server_port}', s3_bucket='synthetic-test',
            s3_access_key='synthetic', s3_secret_key='synthetic', s3_region='auto', s3_addressing_style='path')
        storage = S3Storage(settings)
        try:
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'brief.txt'
                path.write_bytes(b'Brief')
                with self.assertRaises(ClientError):
                    await storage.put('synthetic-key', path)
            self.assertEqual(requests, [b'Brief'], 'A hidden retry can leave an earlier PUT pending after a later success.')
        finally:
            storage.client.close()
            await asyncio.to_thread(server.shutdown)
            server.server_close()
            thread.join(timeout=5)
