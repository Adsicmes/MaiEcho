from __future__ import annotations

import logging
from pathlib import Path

from maiecho_py.internal.config.models import LogConfig

_last_log_entry = ""


class _LastLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        global _last_log_entry
        _last_log_entry = self.format(record)


def configure_logging(config: LogConfig) -> None:
    log_level = getattr(logging, config.level.upper(), logging.INFO)
    log_path = Path(config.output_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)

    memory_handler = _LastLogHandler()
    memory_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(memory_handler)


def get_last_log_entry() -> str:
    return _last_log_entry
