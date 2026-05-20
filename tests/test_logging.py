"""Tests for src.logging_setup."""
import logging
import sys

import pytest

from src.logging_setup import configure_access_log, configure_logging


@pytest.fixture(autouse=True)
def _reset_logging():
    """Restore root + access logger state after each test.

    configure_logging mutates the global root logger; without this the
    surrounding test session's logging would be left in whatever state
    the last test put it in.
    """
    root = logging.getLogger()
    saved_root_handlers = list(root.handlers)
    saved_root_level = root.level

    access = logging.getLogger("access")
    saved_access_handlers = list(access.handlers)
    saved_access_level = access.level
    saved_access_propagate = access.propagate

    yield

    for h in list(root.handlers):
        root.removeHandler(h)
    for h in saved_root_handlers:
        root.addHandler(h)
    root.setLevel(saved_root_level)

    for h in list(access.handlers):
        access.removeHandler(h)
    for h in saved_access_handlers:
        access.addHandler(h)
    access.setLevel(saved_access_level)
    access.propagate = saved_access_propagate


def _get_test_logger():
    return logging.getLogger("iframix.tests.logging_setup")


class TestConfigureLogging:

    def test_log_file_routing(self, tmp_path):
        out = tmp_path / "out.log"
        err = tmp_path / "err.log"
        configure_logging(log_file=str(out), error_log_file=str(err))

        log = _get_test_logger()
        log.info("hello info")
        log.error("hello error")

        for h in logging.getLogger().handlers:
            h.flush()

        assert "hello info" in out.read_text(encoding="utf-8")
        assert "hello error" not in out.read_text(encoding="utf-8")
        assert "hello error" in err.read_text(encoding="utf-8")
        assert "hello info" not in err.read_text(encoding="utf-8")

    def test_default_routing_to_streams(self, capsys):
        configure_logging()

        log = _get_test_logger()
        log.info("info-line")
        log.warning("warn-line")
        for h in logging.getLogger().handlers:
            h.flush()

        captured = capsys.readouterr()
        assert "info-line" in captured.out
        assert "info-line" not in captured.err
        assert "warn-line" in captured.err
        assert "warn-line" not in captured.out

    def test_idempotent(self, capsys):
        configure_logging()
        configure_logging()
        assert len(logging.getLogger().handlers) == 2

    def test_default_level_excludes_debug(self, capsys):
        configure_logging()

        log = _get_test_logger()
        log.debug("debug-line")
        for h in logging.getLogger().handlers:
            h.flush()

        captured = capsys.readouterr()
        assert "debug-line" not in captured.out
        assert "debug-line" not in captured.err

    def test_debug_level_includes_debug(self, capsys):
        configure_logging(level="DEBUG")

        log = _get_test_logger()
        log.debug("debug-line")
        for h in logging.getLogger().handlers:
            h.flush()

        captured = capsys.readouterr()
        assert "debug-line" in captured.out

    def test_invalid_level_raises(self):
        with pytest.raises(ValueError):
            configure_logging(level="TRACE")

    def test_lowercase_level_accepted(self, capsys):
        configure_logging(level="debug")

        log = _get_test_logger()
        log.debug("dbg")
        for h in logging.getLogger().handlers:
            h.flush()

        assert "dbg" in capsys.readouterr().out


class TestConfigureAccessLog:

    def test_access_log_to_file_isolated_from_main_log(self, tmp_path):
        main_log = tmp_path / "main.log"
        configure_logging(log_file=str(main_log))
        access = configure_access_log(str(tmp_path / "access.log"))

        access.info('127.0.0.1 "GET /foo HTTP/1.1"')
        for h in access.handlers:
            h.flush()
        for h in logging.getLogger().handlers:
            h.flush()

        access_text = (tmp_path / "access.log").read_text(encoding="utf-8")
        assert "127.0.0.1" in access_text
        assert 'GET /foo HTTP/1.1' in access_text

        # Access lines must not bleed into the main log file.
        assert "127.0.0.1" not in main_log.read_text(encoding="utf-8")

    def test_access_log_default_to_stdout(self, capsys):
        access = configure_access_log()

        access.info("hit")
        for h in access.handlers:
            h.flush()

        assert "hit" in capsys.readouterr().out

    def test_access_log_does_not_propagate(self, capsys):
        configure_logging()
        access = configure_access_log()

        access.info("only-once")
        for h in access.handlers:
            h.flush()
        for h in logging.getLogger().handlers:
            h.flush()

        captured = capsys.readouterr()
        # Exactly one occurrence — no duplication via root propagation.
        assert captured.out.count("only-once") == 1

    def test_idempotent(self):
        access1 = configure_access_log()
        access2 = configure_access_log()
        assert access1 is access2
        assert len(access1.handlers) == 1
