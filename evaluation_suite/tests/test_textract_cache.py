"""Unit tests for textract_cache.py."""

from unittest.mock import MagicMock, patch

from evaluation_suite.search_evaluation.multi_case import textract_cache as tc

_MOD = "evaluation_suite.search_evaluation.multi_case.textract_cache"
_SAMPLE_URI = "s3://mod-platform-sandbox-kta-documents-bucket/26-700001/doc.pdf"
_SAMPLE_RESPONSE = {"JobStatus": "SUCCEEDED", "Blocks": [{"BlockType": "PAGE"}]}


# ---------------------------------------------------------------------------
# _cache_path
# ---------------------------------------------------------------------------


def test_cache_path_contains_hex_prefix():
    path = tc._cache_path(_SAMPLE_URI)
    assert len(path.stem.split("_")[0]) == 16
    assert all(c in "0123456789abcdef" for c in path.stem.split("_")[0])


def test_cache_path_suffix_is_json():
    assert tc._cache_path(_SAMPLE_URI).suffix == ".json"


def test_cache_path_is_deterministic():
    assert tc._cache_path(_SAMPLE_URI) == tc._cache_path(_SAMPLE_URI)


def test_cache_path_differs_for_different_uris():
    other = "s3://other-bucket/other-key.pdf"
    assert tc._cache_path(_SAMPLE_URI) != tc._cache_path(other)


# ---------------------------------------------------------------------------
# _load / _save round-trip
# ---------------------------------------------------------------------------


def test_load_returns_none_when_missing(tmp_path):
    with patch.object(tc, "_CACHE_DIR", tmp_path):
        assert tc._load(_SAMPLE_URI) is None


def test_save_then_load_round_trips(tmp_path):
    with patch.object(tc, "_CACHE_DIR", tmp_path):
        tc._save(_SAMPLE_URI, _SAMPLE_RESPONSE)
        result = tc._load(_SAMPLE_URI)
    assert result == _SAMPLE_RESPONSE


def test_save_creates_cache_dir(tmp_path):
    cache_dir = tmp_path / "new_cache"
    with patch.object(tc, "_CACHE_DIR", cache_dir):
        tc._save(_SAMPLE_URI, _SAMPLE_RESPONSE)
    assert cache_dir.exists()


# ---------------------------------------------------------------------------
# _resolve_uri
# ---------------------------------------------------------------------------


def test_resolve_uri_remaps_when_mod_platform_mode(monkeypatch):
    monkeypatch.setattr(
        "ingestion_pipeline.config.settings",
        MagicMock(
            USE_MOD_PLATFORM_MODE=True,
            AWS_LOCAL_DEV_TEXTRACT_S3_ROOT_BUCKET="mod-platform-sandbox-kta-documents-bucket",
        ),
    )
    result = tc._resolve_uri("s3://local-kta-documents-bucket/26-700001/doc.pdf")
    assert result == "s3://mod-platform-sandbox-kta-documents-bucket/26-700001/doc.pdf"


def test_resolve_uri_unchanged_when_not_mod_platform_mode(monkeypatch):
    monkeypatch.setattr(
        "ingestion_pipeline.config.settings",
        MagicMock(USE_MOD_PLATFORM_MODE=False),
    )
    uri = "s3://local-kta-documents-bucket/26-700001/doc.pdf"
    assert tc._resolve_uri(uri) == uri


# ---------------------------------------------------------------------------
# _cached_process_document
# ---------------------------------------------------------------------------


@patch(f"{_MOD}.parse")
@patch(f"{_MOD}._load")
@patch(f"{_MOD}._resolve_uri")
def test_cached_process_document_cache_hit_skips_original(mock_resolve, mock_load, mock_parse):
    """On a cache hit, parse(cached) is returned and original process_document is not called."""
    mock_resolve.return_value = _SAMPLE_URI
    mock_load.return_value = _SAMPLE_RESPONSE
    mock_parse.return_value = MagicMock()

    original = MagicMock()
    tc._original_process_document = original

    processor = MagicMock()
    result = tc._cached_process_document(processor, "s3://any-bucket/doc.pdf")

    mock_load.assert_called_once_with(_SAMPLE_URI)
    mock_parse.assert_called_once_with(_SAMPLE_RESPONSE)
    original.assert_not_called()
    assert result is mock_parse.return_value


@patch(f"{_MOD}._resolve_uri")
@patch(f"{_MOD}._load")
def test_cached_process_document_cache_miss_calls_original(mock_load, mock_resolve):
    """On a cache miss, _original_process_document is called."""
    mock_resolve.return_value = _SAMPLE_URI
    mock_load.return_value = None

    original = MagicMock(return_value=MagicMock())
    tc._original_process_document = original

    processor = MagicMock()
    result = tc._cached_process_document(processor, "s3://any-bucket/doc.pdf")

    original.assert_called_once_with(processor, "s3://any-bucket/doc.pdf")
    assert result is original.return_value


@patch(f"{_MOD}._resolve_uri")
@patch(f"{_MOD}._load")
def test_cached_process_document_sets_and_clears_cache_uri(mock_load, mock_resolve):
    """_textract_cache_uri is set before delegating and cleared afterward."""
    mock_resolve.return_value = _SAMPLE_URI
    mock_load.return_value = None

    captured_uri: list[str | None] = []

    def capture_uri(self, uri):
        captured_uri.append(getattr(self, "_textract_cache_uri", None))
        return MagicMock()

    tc._original_process_document = capture_uri

    processor = MagicMock()
    processor._textract_cache_uri = None
    tc._cached_process_document(processor, "s3://any-bucket/doc.pdf")

    assert captured_uri[0] == _SAMPLE_URI
    assert processor._textract_cache_uri is None


# ---------------------------------------------------------------------------
# _cached_get_job_results
# ---------------------------------------------------------------------------


@patch(f"{_MOD}.parse")
@patch(f"{_MOD}._save")
@patch(f"{_MOD}.get_full_json")
def test_cached_get_job_results_saves_when_uri_set(mock_get_full, mock_save, mock_parse):
    """Saves response to cache when _textract_cache_uri is set on the instance."""
    mock_get_full.return_value = _SAMPLE_RESPONSE
    mock_parse.return_value = MagicMock()

    processor = MagicMock()
    processor._textract_cache_uri = _SAMPLE_URI

    result = tc._cached_get_job_results(processor, "job-123")

    mock_save.assert_called_once_with(_SAMPLE_URI, _SAMPLE_RESPONSE)
    mock_parse.assert_called_once_with(_SAMPLE_RESPONSE)
    assert result is mock_parse.return_value


@patch(f"{_MOD}.parse")
@patch(f"{_MOD}._save")
@patch(f"{_MOD}.get_full_json")
def test_cached_get_job_results_no_save_without_uri(mock_get_full, mock_save, mock_parse):
    """Does not call _save when no _textract_cache_uri is set."""
    from types import SimpleNamespace

    mock_get_full.return_value = _SAMPLE_RESPONSE
    # SimpleNamespace with no _textract_cache_uri attribute → getattr returns None
    processor = SimpleNamespace(textract_client=MagicMock())

    tc._cached_get_job_results(processor, "job-456")

    mock_save.assert_not_called()


# ---------------------------------------------------------------------------
# install_cache
# ---------------------------------------------------------------------------


def test_install_cache_patches_process_document():
    """install_cache replaces TextractProcessor.process_document."""
    import ingestion_pipeline.textract.textract_processor as tp_module

    original_pd = tp_module.TextractProcessor.process_document
    original_gjr = tp_module.TextractProcessor._get_job_results
    try:
        tc.install_cache()
        assert tp_module.TextractProcessor.process_document is tc._cached_process_document
        assert tp_module.TextractProcessor._get_job_results is tc._cached_get_job_results
    finally:
        tp_module.TextractProcessor.process_document = original_pd
        tp_module.TextractProcessor._get_job_results = original_gjr


def test_install_cache_stores_originals():
    """install_cache saves the original methods for delegation."""
    import ingestion_pipeline.textract.textract_processor as tp_module

    original_pd = tp_module.TextractProcessor.process_document
    original_gjr = tp_module.TextractProcessor._get_job_results
    try:
        tc.install_cache()
        assert tc._original_process_document is original_pd
        assert tc._original_get_job_results is original_gjr
    finally:
        tp_module.TextractProcessor.process_document = original_pd
        tp_module.TextractProcessor._get_job_results = original_gjr
