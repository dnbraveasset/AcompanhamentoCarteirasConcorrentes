"""Configuração de logging (arquivo + console)."""
from __future__ import annotations

import logging
from pathlib import Path

from config import settings


def obter_logger(nome: str = "fidc_cda") -> logging.Logger:
    logger = logging.getLogger(nome)
    if logger.handlers:  # já configurado
        return logger

    logger.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))

    Path(settings.LOGS_DIR).mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(settings.LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger
