"""Entry point for the DDNS agent."""

from __future__ import annotations

import logging
import signal
import threading
from typing import Optional

from agent.core import DDNSRunner


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def main() -> int:
    _configure_logging()
    runner = DDNSRunner()
    reload_event = threading.Event()
    stop_event = threading.Event()

    def handle_sighup(signum: int, frame: Optional[object]) -> None:
        logging.info("Received SIGHUP; scheduling config reload.")
        reload_event.set()

    def handle_sigterm(signum: int, frame: Optional[object]) -> None:
        logging.info("Received SIGTERM; stopping agent.")
        stop_event.set()

    signal.signal(signal.SIGHUP, handle_sighup)
    signal.signal(signal.SIGTERM, handle_sigterm)

    runner.load_config()

    try:
        while not stop_event.is_set():
            if reload_event.is_set():
                runner.load_config()
                reload_event.clear()
                logging.info("Configuration reloaded.")
            runner.run_once()
            sleep_seconds = runner.get_sleep_seconds()
            stop_event.wait(timeout=sleep_seconds)
    finally:
        runner.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
