"""Processo residente iniciado no logon; sincroniza imediatamente e a cada 6h."""

from __future__ import annotations

import logging
import msvcrt
import os
import time
from pathlib import Path

import sync_once


def main() -> int:
    interval_hours = max(1, int(os.environ.get("ALLCARE_SYNC_INTERVAL_HOURS", "6")))
    runtime_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Hermes"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    lock_file = open(runtime_dir / "allcare-agent.lock", "a+b")
    try:
        lock_file.seek(0)
        if lock_file.tell() == 0:
            lock_file.write(b"0")
            lock_file.flush()
        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        return 0

    sync_once.configure_logging()
    logging.info("Agente Allcare residente iniciado; intervalo de %d hora(s).", interval_hours)
    while True:
        try:
            sync_once.main()
        except Exception as error:
            logging.exception("Falha inesperada no ciclo Allcare: %s", error)
        time.sleep(interval_hours * 60 * 60)


if __name__ == "__main__":
    raise SystemExit(main())
