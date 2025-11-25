import logging

from ingestion_pipeline.custom_logging.log_context import ContextFilter, setup_logging, source_doc_id_context


def create_log_record(msg):
    # Create a real LogRecord for testing
    return logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=0, msg=msg, args=(), exc_info=None
    )


def test_context_filter_injects_source_doc_id():
    # Set the context variable
    source_doc_id_context.set("doc-123")
    record = create_log_record("Test message")
    f = ContextFilter()
    result = f.filter(record)
    assert result is True
    assert record.msg.startswith("doc-123 ")
    assert "Test message" in record.msg


def test_context_filter_no_source_doc_id():
    # Reset context variable
    source_doc_id_context.set(None)
    record = create_log_record("Test message")
    f = ContextFilter()
    result = f.filter(record)
    assert result is True
    assert record.msg == "Test message"


def test_setup_logging_sets_root_logger(monkeypatch):
    # Patch root logger and StreamHandler
    class DummyHandler(logging.StreamHandler):
        def __init__(self):
            super().__init__()
            self.filters = []
            self.formatter = None

        def setFormatter(self, fmt):
            self.formatter = fmt

        def addFilter(self, filter):
            self.filters.append(filter)

    dummy_logger = logging.getLogger("test_logger")
    monkeypatch.setattr(logging, "getLogger", lambda: dummy_logger)
    dummy_logger.handlers.clear()
    monkeypatch.setattr(logging, "StreamHandler", DummyHandler)

    setup_logging()
    # Should have one handler
    assert len(dummy_logger.handlers) == 1
    handler = dummy_logger.handlers[0]
    # Should have ContextFilter
    assert any(isinstance(f, ContextFilter) for f in handler.filters)
    # Should have a formatter
    assert handler.formatter is not None
    # Should set log level to INFO
    assert dummy_logger.level == logging.INFO
