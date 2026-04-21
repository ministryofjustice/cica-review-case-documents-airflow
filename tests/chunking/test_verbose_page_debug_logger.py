import logging

import pytest

from ingestion_pipeline.chunking import verbose_page_debug_logger as vlogger


@pytest.fixture(autouse=True)
def patch_debug_page_numbers(monkeypatch):
    # Patch DEBUG_PAGE_NUMBERS to a known value for tests
    monkeypatch.setattr(vlogger, "DEBUG_PAGE_NUMBERS", {1, 2, 99})


@pytest.fixture
def caplog_debug_level(caplog):
    caplog.set_level(logging.DEBUG)
    return caplog


def test_is_verbose_page_debug_logs_context_auto_detection(caplog_debug_level):
    # Should log when page_number is in DEBUG_PAGE_NUMBERS and context is auto-detected
    with caplog_debug_level.at_level(logging.DEBUG):
        result = vlogger.is_verbose_page_debug(1)
    assert result is True
    assert any("Extra logging enabled for page 1" in rec.message for rec in caplog_debug_level.records)
    assert any("[" in rec.message and "]" in rec.message for rec in caplog_debug_level.records)


def test_is_verbose_page_debug_returns_false_and_no_log_when_not_enabled(caplog_debug_level):
    with caplog_debug_level.at_level(logging.DEBUG):
        result = vlogger.is_verbose_page_debug(42)
    assert result is False
    assert not caplog_debug_level.records


def test_log_verbose_page_debug_logs_with_auto_context(caplog_debug_level):
    with caplog_debug_level.at_level(logging.DEBUG):
        vlogger.log_verbose_page_debug(2, "Test message")
    assert any("Test message" in rec.message for rec in caplog_debug_level.records)
    assert any("[" in rec.message and "]" in rec.message for rec in caplog_debug_level.records)


def test_log_verbose_page_debug_no_log_when_not_enabled(caplog_debug_level):
    with caplog_debug_level.at_level(logging.DEBUG):
        vlogger.log_verbose_page_debug(123, "Should not log")
    assert not caplog_debug_level.records


def test_log_verbose_page_debug_with_explicit_context(caplog_debug_level):
    with caplog_debug_level.at_level(logging.DEBUG):
        vlogger.log_verbose_page_debug(99, "Explicit context message", context="mycontext")
    assert any("[mycontext]" in rec.message for rec in caplog_debug_level.records)
    assert any("Explicit context message" in rec.message for rec in caplog_debug_level.records)

    def test_is_verbose_page_debug_context_no_module(caplog_debug_level):
        # Dynamically create a function so inspect.getmodule returns None
        code = """
    def dynamic_func():
        from ingestion_pipeline.chunking import verbose_page_debug_logger as vlogger
        return vlogger.is_verbose_page_debug(1)
    """
        local_vars = {}
        exec(code, {}, local_vars)
        dynamic_func = local_vars["dynamic_func"]
        with caplog_debug_level.at_level(logging.DEBUG):
            result = dynamic_func()
        assert result is True
        # The context should be just the function name (dynamic_func)
        assert any("[dynamic_func]" in rec.message for rec in caplog_debug_level.records)

    def test_log_verbose_page_debug_context_no_module(caplog_debug_level):
        # Dynamically create a function so inspect.getmodule returns None
        code = """
    def dynamic_func():
        from ingestion_pipeline.chunking import verbose_page_debug_logger as vlogger
        vlogger.log_verbose_page_debug(1, 'No module context')
    """
        local_vars = {}
        exec(code, {}, local_vars)
        dynamic_func = local_vars["dynamic_func"]
        with caplog_debug_level.at_level(logging.DEBUG):
            dynamic_func()
        # The context should be just the function name (dynamic_func)
        assert any("[dynamic_func] No module context" in rec.message for rec in caplog_debug_level.records)
