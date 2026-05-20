"""Shared logging configuration for the router and API server.

Provides two helpers:

- ``configure_logging`` sets up the root logger with a stdout/INFO handler
  and a stderr/WARNING handler (or file equivalents), at a configurable
  level.
- ``configure_access_log`` returns a dedicated ``access`` logger for the
  API server's per-request HTTP access log, optionally writing to its own
  file rather than stdout.
"""

import logging
import os
import sys

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
ACCESS_LOG_FORMAT = "%(asctime)s %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class _MaxLevelFilter(logging.Filter):
    """Allow records strictly below ``ceiling`` (so INFO handler skips warnings)."""

    def __init__(self, ceiling):
        super().__init__()
        self.ceiling = ceiling

    def filter(self, record):
        return record.levelno < self.ceiling


def _resolve_level(level):
    if isinstance(level, int):
        return level
    name = str(level).upper()
    # logging.getLevelName(name) returns the int for known names and the
    # string "Level <name>" for unknown ones. Avoids
    # logging.getLevelNamesMapping(), which is Python 3.11+.
    value = logging.getLevelName(name)
    if not isinstance(value, int):
        raise ValueError(f"Unknown log level: {level!r}")
    return value


def _ensure_parent_dir(path):
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def _make_handler(path, stream):
    if path:
        _ensure_parent_dir(path)
        return logging.FileHandler(path, mode="a", encoding="utf-8")
    return logging.StreamHandler(stream)


def configure_logging(log_file=None, error_log_file=None, level="INFO"):
    """Configure the root logger.

    INFO/DEBUG records go to ``log_file`` (or stdout); WARNING and above go
    to ``error_log_file`` (or stderr). The two handlers never duplicate.
    Calling this more than once replaces the existing configuration.
    """
    resolved = _resolve_level(level)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass
    root.setLevel(resolved)

    info_handler = _make_handler(log_file, sys.stdout)
    info_handler.setLevel(resolved)
    info_handler.addFilter(_MaxLevelFilter(logging.WARNING))
    info_handler.setFormatter(formatter)
    root.addHandler(info_handler)

    error_handler = _make_handler(error_log_file, sys.stderr)
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(formatter)
    root.addHandler(error_handler)


def configure_access_log(access_log_file=None):
    """Configure and return the dedicated ``access`` logger.

    The access logger does not propagate to the root logger, so its
    records never bleed into ``--log-file``. With ``access_log_file``
    unset, lines go to stdout (today's behaviour).
    """
    formatter = logging.Formatter(ACCESS_LOG_FORMAT, datefmt=DATE_FORMAT)

    logger = logging.getLogger("access")
    for h in list(logger.handlers):
        logger.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass
    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = _make_handler(access_log_file, sys.stdout)
    handler.setLevel(logging.INFO)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
