import asyncio
import logging
from ..runtime import loop_factory
from ..settings import Settings
from .runtime import configure_logging, run_process, shutdown_signals


async def serve(settings):
    stop = asyncio.Event()
    async with shutdown_signals(stop):
        await run_process(settings, stop_event=stop)


def main():
    settings = Settings.from_env(load_file=True)
    configure_logging(settings)
    try:
        with asyncio.Runner(loop_factory=loop_factory) as runner:
            runner.run(serve(settings))
    except KeyboardInterrupt:
        pass
    except Exception:
        logging.getLogger(__name__).error('Bot process stopped; check configuration and service readiness.')
        raise SystemExit(1) from None


if __name__ == '__main__': main()
