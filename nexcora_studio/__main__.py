import asyncio
import os
import uvicorn
from .app import create_app
from .runtime import loop_factory
from .settings import Settings


def main():
    settings = Settings.from_env(load_file=True)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host='127.0.0.1' if settings.development else '0.0.0.0', port=int(os.environ.get('PORT', '8000')), access_log=False, proxy_headers=False, limit_concurrency=32, timeout_keep_alive=5))
    asyncio.run(server.serve(), loop_factory=loop_factory)


if __name__ == '__main__':
    main()
