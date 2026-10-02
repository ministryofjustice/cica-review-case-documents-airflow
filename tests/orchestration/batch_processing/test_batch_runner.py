import logging
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import pytest
from hypothesis import HealthCheck, given, settings as hyp_settings, strategies as st

from ingestion_pipeline.chunking.schemas import DocumentMetadata
from ingestion_pipeline.document_identity.identity import compute_source_doc_id
from ingestion_pipeline.errors import DlqCategory, EmptyTextractResponseError, PipelineError, ZeroChunksError
from ingestion_pipeline.orchestration.batch_processing.batch_runner import process_document_job, run_batch
from ingestion_pipeline.orchestration.document_source import DocumentJob
from ingestion_pipeline.uuid_generators.document_uuid import DocumentIdentifier

"""Tests for the batch runner module (worker logic and batch orchestration)."""


@pytest.fixture(autouse=True)
def patch_settings():
    with mock.patch("ingestion_pipeline.orchestration.batch_processing.batch_runner.settings") as mock_settings:
        mock_settings.AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET = "test-kta-documents-bucket"
        mock_settings.AWS_CICA_S3_SOURCE_DOCUMENT_CASE_PREFIX = "26-711111"
        mock_settings.AWS_CICA_S3_SOURCE_DOCUMENT_FILENAME = "Case1_TC19_50_pages_brain_injury.pdf"
        mock_settings.MAX_CONCURRENT_DOCUMENTS = 4
        mock_settings.OPENSEARCH_PROXY_URL = "http://localhost:9200"
        mock_settings.OPENSEARCH_VERIFY_CERTS = True
        mock_settings.OPENSEARCH_SSL_ASSERT_HOSTNAME = True
        mock_settings.LOCAL_DEVELOPMENT_MODE = False
        yield mock_settings


def _make_job(
    s3_uri: str = "s3://test-kta-documents-bucket/26-711111/Case1_TC19_50_pages_brain_injury.pdf",
    case_ref: str = "26-711111",
) -> DocumentJob:
    return DocumentJob(
        source_file_s3_uri=s3_uri,
        correspondence_type="TC19 - ADDITIONAL INFO REQUEST",
        case_ref=case_ref,
    )


# --- process_document_job -------------------------------------------------


def test_process_document_job_success_builds_metadata_and_runs_pipeline():
    """A valid job runs the pipeline and, on a clean return, reports success."""
    pipeline = mock.Mock()
    pipeline.process_document.return_value = None
    job = _make_job()

    result = process_document_job(job, pipeline)

    assert result.success is True
    assert result.error is None
    assert result.category is None
    assert result.retryable is None
    assert result.source_doc_id
    pipeline.process_document.assert_called_once()

    metadata = pipeline.process_document.call_args.kwargs["document_metadata"]
    assert isinstance(metadata, DocumentMetadata)
    assert metadata.source_file_name == "Case1_TC19_50_pages_brain_injury.pdf"
    assert metadata.case_ref == "26-711111"
    assert metadata.correspondence_type == "TC19 - ADDITIONAL INFO REQUEST"
    assert metadata.page_count is None


def test_process_document_job_invalid_uri_is_contained():
    """An invalid S3 URI is caught and reported as an unexpected, non-retryable failure."""
    pipeline = mock.Mock()
    job = _make_job(s3_uri="s3://test-kta-documents-bucket/not-a-case-ref/file.pdf", case_ref="not-a-case-ref")

    result = process_document_job(job, pipeline)

    assert result.success is False
    assert isinstance(result.error, ValueError)
    assert result.category is DlqCategory.UNEXPECTED
    assert result.retryable is False
    pipeline.process_document.assert_not_called()


def test_process_document_job_contains_unexpected_exception(caplog):
    """An unexpected (non-PipelineError) failure is contained and classified UNEXPECTED."""
    pipeline = mock.Mock()
    pipeline.process_document.side_effect = RuntimeError("boom")
    job = _make_job()

    with caplog.at_level(logging.CRITICAL, logger="ingestion_pipeline.orchestration.batch_processing.batch_runner"):
        result = process_document_job(job, pipeline)

    assert result.success is False
    assert isinstance(result.error, RuntimeError)
    assert result.category is DlqCategory.UNEXPECTED
    assert result.retryable is False

    critical_records = [
        record
        for record in caplog.records
        if record.levelno == logging.CRITICAL
        and "Pipeline runner encountered an unexpected error" in record.getMessage()
    ]
    assert critical_records
    assert critical_records[-1].exc_info is not None
    assert critical_records[-1].exc_info[0] is RuntimeError


@pytest.mark.parametrize(
    ("exception", "expected_category"),
    [
        (
            EmptyTextractResponseError("no document", source_doc_id="d", case_ref="c", s3_uri="s"),
            DlqCategory.EMPTY_TEXTRACT_RESPONSE,
        ),
        (
            ZeroChunksError("no chunks", source_doc_id="d", case_ref="c", s3_uri="s"),
            DlqCategory.ZERO_CHUNKS_EXTRACTED_FROM_DOCUMENT,
        ),
    ],
)
def test_process_document_job_pipeline_error_is_not_success(caplog, exception, expected_category):
    """A classified PipelineError is contained, recorded with its category, and not a success."""
    pipeline = mock.Mock()
    pipeline.process_document.side_effect = exception
    job = _make_job()

    with caplog.at_level(logging.ERROR, logger="ingestion_pipeline.orchestration.batch_processing.batch_runner"):
        result = process_document_job(job, pipeline)

    assert result.success is False
    assert result.error is exception
    assert result.category is expected_category
    assert result.retryable is False
    pipeline.process_document.assert_called_once()
    assert any("not acknowledging" in record.getMessage() for record in caplog.records)


def test_process_document_job_resets_log_context():
    """The source_doc_id context is reset after processing (no leak across threads)."""
    from ingestion_pipeline.custom_logging.log_context import source_doc_id_context

    pipeline = mock.Mock()
    pipeline.process_document.return_value = None
    process_document_job(_make_job(), pipeline)

    assert source_doc_id_context.get() is None


# --- run_batch ------------------------------------------------------------


def test_run_batch_empty_returns_no_results():
    pipeline = mock.Mock()
    source = mock.Mock()

    result = run_batch([], pipeline, source, batch_number=1)

    assert result.results == []
    assert result.summary.jobs_in_batch == 0
    assert result.summary.batch_number == 1
    pipeline.process_document.assert_not_called()
    source.acknowledge.assert_not_called()


def test_run_batch_processes_all_and_acknowledges_only_successes():
    pipeline = mock.Mock()
    pipeline.process_document.return_value = None
    source = mock.Mock()

    good = _make_job()
    bad = _make_job(s3_uri="s3://test-kta-documents-bucket/bad/file.pdf", case_ref="bad")

    results = run_batch([good, bad], pipeline, source, batch_number=1).results

    assert len(results) == 2
    successes = [r for r in results if r.success]
    failures = [r for r in results if not r.success]
    assert len(successes) == 1
    assert len(failures) == 1

    # Only the successful job is acknowledged.
    source.acknowledge.assert_called_once()
    assert source.acknowledge.call_args.args[0] is good


def test_run_batch_caps_workers_at_max_concurrent_documents(patch_settings):
    """The pool is sized at min(MAX_CONCURRENT_DOCUMENTS, len(jobs)).

    With more jobs than the configured limit, the pool must be capped at the
    limit (not at the job count). Guards against a wrong worker-count regression
    that the small-batch tests would not catch.
    """
    patch_settings.MAX_CONCURRENT_DOCUMENTS = 3
    pipeline = mock.Mock()
    pipeline.process_document.return_value = None
    source = mock.Mock()

    jobs = [_make_job(s3_uri=f"s3://test-kta-documents-bucket/26-711111/doc{i}.pdf") for i in range(10)]

    captured_max_workers: list[int] = []
    real_executor = ThreadPoolExecutor

    def _recording_executor(max_workers, *args, **kwargs):
        captured_max_workers.append(max_workers)
        return real_executor(max_workers=max_workers, *args, **kwargs)

    with mock.patch(
        "ingestion_pipeline.orchestration.batch_processing.batch_runner.ThreadPoolExecutor",
        side_effect=_recording_executor,
    ):
        results = run_batch(jobs, pipeline, source, batch_number=1).results

    assert len(results) == 10
    # min(3, 10) == 3: capped at the limit, not the job count.
    assert captured_max_workers == [3]


def test_run_batch_caps_workers_at_job_count_when_fewer_jobs(patch_settings):
    """When jobs are fewer than the limit, the pool is sized to the job count."""
    patch_settings.MAX_CONCURRENT_DOCUMENTS = 8
    pipeline = mock.Mock()
    pipeline.process_document.return_value = None
    source = mock.Mock()

    jobs = [_make_job(s3_uri=f"s3://test-kta-documents-bucket/26-711111/doc{i}.pdf") for i in range(2)]

    captured_max_workers: list[int] = []
    real_executor = ThreadPoolExecutor

    def _recording_executor(max_workers, *args, **kwargs):
        captured_max_workers.append(max_workers)
        return real_executor(max_workers=max_workers, *args, **kwargs)

    with mock.patch(
        "ingestion_pipeline.orchestration.batch_processing.batch_runner.ThreadPoolExecutor",
        side_effect=_recording_executor,
    ):
        run_batch(jobs, pipeline, source, batch_number=1)

    # min(8, 2) == 2: capped at the job count.
    assert captured_max_workers == [2]


def test_run_batch_executes_documents_concurrently(patch_settings):
    """Workers run in parallel: MAX_CONCURRENT_DOCUMENTS documents overlap in time.

    Each ``process_document`` call blocks on a barrier sized to the limit. If the
    runner processed documents serially the barrier would never be satisfied and
    the calls would time out, so this asserts genuine concurrency rather than a
    serial loop that happens to return the right results.
    """
    limit = 4
    patch_settings.MAX_CONCURRENT_DOCUMENTS = limit

    # A barrier that only releases once `limit` threads have arrived. A serial
    # implementation would deadlock here and trip the timeout below.
    barrier = threading.Barrier(limit, timeout=5)
    max_observed_concurrency = 0
    concurrency_lock = threading.Lock()
    current_concurrency = 0

    def _blocking_process(*_args, **_kwargs):
        nonlocal max_observed_concurrency, current_concurrency
        with concurrency_lock:
            current_concurrency += 1
            max_observed_concurrency = max(max_observed_concurrency, current_concurrency)
        # Wait until `limit` workers are running at once; raises BrokenBarrierError
        # (failing the test) if they never all arrive within the timeout.
        barrier.wait()
        with concurrency_lock:
            current_concurrency -= 1

    pipeline = mock.Mock()
    pipeline.process_document.side_effect = _blocking_process
    source = mock.Mock()

    jobs = [_make_job(s3_uri=f"s3://test-kta-documents-bucket/26-711111/doc{i}.pdf") for i in range(limit)]

    results = run_batch(jobs, pipeline, source, batch_number=1).results

    assert len(results) == limit
    assert all(r.success for r in results)
    assert max_observed_concurrency == limit


@pytest.mark.parametrize(
    "exception",
    [
        EmptyTextractResponseError("no document", source_doc_id="d", case_ref="c", s3_uri="s"),
        ZeroChunksError("no chunks", source_doc_id="d", case_ref="c", s3_uri="s"),
    ],
)
def test_run_batch_does_not_acknowledge_pipeline_failure(exception):
    """A terminal PipelineError leaves the job unacknowledged so SQS can redrive it."""
    pipeline = mock.Mock()
    pipeline.process_document.side_effect = exception
    source = mock.Mock()

    job = _make_job()

    results = run_batch([job], pipeline, source, batch_number=1).results

    assert len(results) == 1
    assert results[0].success is False
    assert isinstance(results[0].error, PipelineError)
    source.acknowledge.assert_not_called()


# --- Bug condition exploration: duplicate source_doc_id dedup ------------------
#
# BUGFIX WORKFLOW — exploration tests for spec `duplicate-source-key-dedup`.
#
# These tests encode the EXPECTED (fixed) behaviour described by Property 1 in
# .kiro/specs/duplicate-source-key-dedup/design.md:
#   * each distinct source_doc_id is handed to the pipeline at most once,
#   * no two in-flight units share a source_doc_id (no concurrent collision),
#   * every input job reaches a defined acknowledgement outcome.
#
# They are EXPECTED TO FAIL on the UNFIXED runner: `run_batch` submits every job
# to the ThreadPoolExecutor with no grouping by source_doc_id, so two jobs that
# resolve to the same source_doc_id are processed twice, concurrently, and only
# the exact processed jobs are acknowledged (duplicates are silently dropped).
# The failures are the counterexamples that confirm the bug exists. DO NOT fix
# the test or the code from this task.

_DUP_BUCKET = "test-kta-documents-bucket"


def _expected_source_doc_id(job: DocumentJob) -> str:
    """Compute the deterministic source_doc_id for a job the same way the runner does."""
    return DocumentIdentifier(
        source_file_name=job.source_file_name,
        correspondence_type=job.correspondence_type,
        case_ref=job.case_ref,
    ).generate_uuid()


def _make_dup_job(case_ref: str = "26-711111", file_name: str = "dup.pdf") -> DocumentJob:
    """Build a job whose natural key resolves to a well-known source_doc_id.

    Two jobs built with the same case_ref/file_name (and the shared correspondence
    type) resolve to the same source_doc_id — the bug condition.
    """
    return DocumentJob(
        source_file_s3_uri=f"s3://{_DUP_BUCKET}/{case_ref}/{file_name}",
        correspondence_type="TC19 - ADDITIONAL INFO REQUEST",
        case_ref=case_ref,
    )


class _RecordingSource:
    """In-memory DocumentSource that records every acknowledge() call.

    Stands in for SQS: no AWS calls happen at the run_batch seam, so a plain
    recorder is sufficient (and lets us assert exactly which jobs were acked).
    """

    def __init__(self) -> None:
        self.acknowledged: list[DocumentJob] = []

    def fetch_batch(self) -> list[DocumentJob]:
        return []

    def acknowledge(self, job: DocumentJob) -> None:
        self.acknowledged.append(job)


class _InvocationRecord:
    """Records a single process_document invocation for one source_doc_id."""

    def __init__(self, source_doc_id: str, start: float, end: float) -> None:
        self.source_doc_id = source_doc_id
        self.start = start
        self.end = end

    def overlaps(self, other: "_InvocationRecord") -> bool:
        """True if this invocation's [start, end] window overlaps the other's."""
        return self.start < other.end and other.start < self.end


class _RecordingPipeline:
    """Instrumented fake Pipeline recording every process_document invocation.

    Each call records the invocation keyed by source_doc_id together with entry
    and exit timestamps so overlap between concurrent invocations of the same
    source_doc_id can be detected. A configurable sleep between entry and exit
    widens the window so a genuine concurrent collision is observable.
    """

    def __init__(self, sleep_seconds: float = 0.0, fail_source_doc_ids: set[str] | None = None) -> None:
        self.sleep_seconds = sleep_seconds
        self.fail_source_doc_ids = fail_source_doc_ids or set()
        self._lock = threading.Lock()
        self.invocations: list[_InvocationRecord] = []
        # Tracks source_doc_ids currently inside process_document (for live-overlap detection).
        self._in_flight: Counter = Counter()
        self.observed_concurrent_collision = False

    def process_document(self, document_metadata: DocumentMetadata) -> None:
        source_doc_id = document_metadata.source_doc_id
        start = time.monotonic()
        with self._lock:
            self._in_flight[source_doc_id] += 1
            if self._in_flight[source_doc_id] > 1:
                # Two units are inside process_document for the same id at once.
                self.observed_concurrent_collision = True
        try:
            if self.sleep_seconds:
                time.sleep(self.sleep_seconds)
            if source_doc_id in self.fail_source_doc_ids:
                raise ZeroChunksError(
                    "forced failure",
                    source_doc_id=source_doc_id,
                    case_ref=document_metadata.case_ref,
                    s3_uri=document_metadata.source_file_s3_uri,
                )
        finally:
            end = time.monotonic()
            with self._lock:
                self._in_flight[source_doc_id] -= 1
                self.invocations.append(_InvocationRecord(source_doc_id, start, end))

    def invocation_counts(self) -> Counter:
        """Return a Counter of process_document invocations keyed by source_doc_id."""
        return Counter(rec.source_doc_id for rec in self.invocations)

    def any_same_id_overlap(self) -> bool:
        """True if any two invocations for the same source_doc_id overlapped in time."""
        by_id: dict[str, list[_InvocationRecord]] = {}
        for rec in self.invocations:
            by_id.setdefault(rec.source_doc_id, []).append(rec)
        for records in by_id.values():
            for i in range(len(records)):
                for j in range(i + 1, len(records)):
                    if records[i].overlaps(records[j]):
                        return True
        return False


def _acknowledgement_outcome_defined(job: DocumentJob, source: _RecordingSource, owner_succeeded: bool) -> bool:
    """A job has a defined acknowledgement outcome.

    Defined outcomes ∈ { ack_as_processed, dropped_as_duplicate, left_for_redrive }.
    On owner success every job sharing the id must be acknowledged (ack_as_processed
    for the owner / dropped_as_duplicate for its duplicates). On owner failure every
    such job is left unacknowledged (left_for_redrive).
    """
    was_acked = any(acked is job for acked in source.acknowledged)
    if owner_succeeded:
        return was_acked
    return not was_acked


# --- Test case 1: duplicate-key single invocation ------------------------------


def test_explore_duplicate_key_single_invocation():
    """Property 1: a duplicate-keyed batch invokes the pipeline once per source_doc_id.

    Two jobs share a source_doc_id. The fixed runner processes that id exactly
    once. On UNFIXED code the pipeline is invoked twice for the single id.
    """
    pipeline = _RecordingPipeline()
    source = _RecordingSource()
    job_a = _make_dup_job()
    job_b = _make_dup_job()  # identical natural key -> same source_doc_id
    source_doc_id = _expected_source_doc_id(job_a)
    assert _expected_source_doc_id(job_b) == source_doc_id  # confirms the bug condition

    run_batch([job_a, job_b], pipeline, source, batch_number=1)

    counts = pipeline.invocation_counts()
    assert counts[source_doc_id] <= 1, (
        f"process_document invoked {counts[source_doc_id]}x for a single source_doc_id {source_doc_id} (expected <= 1)"
    )


# --- Test case 2: concurrent collision (slow fake pipeline) --------------------


def test_explore_duplicate_key_no_concurrent_overlap():
    """Property 1: no two invocations for the same source_doc_id overlap in time.

    Uses a slow fake pipeline (enter -> sleep -> exit) to widen the window so a
    genuine concurrent collision is observable. On UNFIXED code both duplicate
    workers enter process_document at once and their windows overlap.
    """
    pipeline = _RecordingPipeline(sleep_seconds=0.3)
    source = _RecordingSource()
    job_a = _make_dup_job()
    job_b = _make_dup_job()
    source_doc_id = _expected_source_doc_id(job_a)

    run_batch([job_a, job_b], pipeline, source, batch_number=1)

    assert not pipeline.observed_concurrent_collision, (
        f"two units were inside process_document concurrently for source_doc_id {source_doc_id}"
    )
    assert not pipeline.any_same_id_overlap(), f"two invocations for source_doc_id {source_doc_id} overlapped in time"


# --- Test case 3: cleanup isolation when one duplicate fails -------------------


def test_explore_duplicate_key_cleanup_isolation_on_failure():
    """Property 1: a failing duplicate must not run concurrently with a sibling unit.

    With two duplicate-keyed jobs where processing fails, the shared source_doc_id
    means a failure-path cleanup would collide with the other in-flight worker. The
    fixed runner guarantees a single owner per id, so at most one unit ever runs
    for that id. On UNFIXED code the id is processed twice and the windows overlap,
    which is exactly the cleanup-collision condition.
    """
    job_a = _make_dup_job()
    job_b = _make_dup_job()
    source_doc_id = _expected_source_doc_id(job_a)

    pipeline = _RecordingPipeline(sleep_seconds=0.3, fail_source_doc_ids={source_doc_id})
    source = _RecordingSource()

    run_batch([job_a, job_b], pipeline, source, batch_number=1)

    counts = pipeline.invocation_counts()
    assert counts[source_doc_id] <= 1, (
        f"failing source_doc_id {source_doc_id} was processed {counts[source_doc_id]}x; "
        f"cleanup for one unit can corrupt the other in-flight unit"
    )
    assert not pipeline.any_same_id_overlap(), (
        f"failing duplicate units overlapped for source_doc_id {source_doc_id} (cleanup collision)"
    )


# --- Test case 4: duplicate acknowledgement (both jobs acked on success) -------


def test_explore_duplicate_key_both_jobs_acknowledged_on_success():
    """Property 1: on owner success every job sharing the id reaches a defined outcome.

    Both duplicate jobs succeed. The fixed runner acknowledges the owner AND its
    duplicate (dropped_as_duplicate). On UNFIXED code only the processed jobs are
    acked and there is no defined outcome for the collapsed duplicate.
    """
    pipeline = _RecordingPipeline()
    source = _RecordingSource()
    job_a = _make_dup_job()
    job_b = _make_dup_job()

    run_batch([job_a, job_b], pipeline, source, batch_number=1)

    assert _acknowledgement_outcome_defined(job_a, source, owner_succeeded=True), (
        "job_a did not reach a defined acknowledgement outcome on success"
    )
    assert _acknowledgement_outcome_defined(job_b, source, owner_succeeded=True), (
        "duplicate job_b was silently dropped without a defined acknowledgement outcome"
    )


# --- Scoped property test: same key repeated N times ---------------------------


@hyp_settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    n=st.integers(min_value=2, max_value=5),
    case_ref=st.sampled_from(["26-711111", "27-800001", "26-700030"]),
    file_name=st.sampled_from(["dup.pdf", "case30.pdf", "brain_injury.pdf"]),
)
def test_explore_property_duplicate_key_repeated_n_times(n, case_ref, file_name):
    """Property 1 (scoped PBT): a key repeated N>=2 times is processed at most once.

    For a batch that repeats one natural key N times (isBugCondition holds), the
    fixed run_batch hands the single source_doc_id to the pipeline at most once,
    never overlaps, and gives every input job a defined acknowledgement outcome.
    On UNFIXED code the id is processed N times, invocations overlap, and only the
    processed jobs are acknowledged.

    Validates: Requirements 1.1, 1.2, 1.3, 1.5, 2.1, 2.2, 2.3, 2.5
    """
    jobs = [_make_dup_job(case_ref=case_ref, file_name=file_name) for _ in range(n)]
    source_doc_id = _expected_source_doc_id(jobs[0])
    # Confirm the bug condition: all jobs share one source_doc_id.
    assert len({_expected_source_doc_id(j) for j in jobs}) == 1

    pipeline = _RecordingPipeline(sleep_seconds=0.05)
    source = _RecordingSource()

    run_batch(jobs, pipeline, source, batch_number=1)

    counts = pipeline.invocation_counts()
    assert counts[source_doc_id] <= 1, (
        f"source_doc_id {source_doc_id} processed {counts[source_doc_id]}x for a batch of {n} identical-key jobs"
    )
    assert not pipeline.any_same_id_overlap(), "duplicate-key invocations overlapped in time"
    # Every input job must reach a defined acknowledgement outcome (all succeed here).
    for job in jobs:
        assert _acknowledgement_outcome_defined(job, source, owner_succeeded=True), (
            "an input job was left without a defined acknowledgement outcome on success"
        )


# --- Preservation property tests: distinct-key batches unchanged ---------------
#
# BUGFIX WORKFLOW — preservation tests for spec `duplicate-source-key-dedup`.
#
# These tests capture the BASELINE behaviour of the UNFIXED `run_batch` for
# batches where NO two jobs share a source_doc_id (isBugCondition is false).
# Property 2 in .kiro/specs/duplicate-source-key-dedup/design.md requires the
# fixed runner to behave EXACTLY as the original for such batches:
#   * concurrency capped at min(MAX_CONCURRENT_DOCUMENTS, len(jobs)),
#   * each succeeding job acknowledged exactly once,
#   * each failing job left unacknowledged with success=False + category/retryable,
#   * one DocumentResult per job, deterministic source_doc_id unchanged,
#   * empty batch -> [].
#
# Following observation-first methodology, these were run against the UNFIXED
# run_batch and encode the OBSERVED outputs. They are EXPECTED TO PASS on the
# unfixed code (they pin the behaviour that must be preserved by the fix).

# A guaranteed-distinct natural key generator. case_ref matches the CICA pattern
# `\d{2}-[78]\d{5}` so the S3 URI validates (success path). Distinct file names
# guarantee distinct natural keys -> distinct source_doc_ids.
_CASE_REF_STRATEGY = st.builds(
    lambda yy, lead, rest: f"{yy:02d}-{lead}{rest:05d}",
    st.integers(min_value=0, max_value=99),
    st.sampled_from(["7", "8"]),
    st.integers(min_value=0, max_value=99999),
)


def _make_distinct_job(index: int, case_ref: str = "26-711111") -> DocumentJob:
    """Build a job with a unique file name so its source_doc_id is distinct.

    The index is folded into the file name, guaranteeing a distinct natural key
    (and therefore a distinct source_doc_id) within a batch.
    """
    return DocumentJob(
        source_file_s3_uri=f"s3://{_DUP_BUCKET}/{case_ref}/distinct_{index}.pdf",
        correspondence_type="TC19 - ADDITIONAL INFO REQUEST",
        case_ref=case_ref,
    )


def _distinct_key_batch(size: int) -> list[DocumentJob]:
    """Build a batch of `size` jobs with guaranteed-distinct natural keys."""
    return [_make_distinct_job(i) for i in range(size)]


def _assert_distinct_source_doc_ids(jobs: list[DocumentJob]) -> None:
    """Confirm the batch does NOT satisfy the bug condition (all ids distinct)."""
    ids = [_expected_source_doc_id(job) for job in jobs]
    assert len(set(ids)) == len(ids), "batch unexpectedly contains duplicate source_doc_ids"


# --- Preservation: distinct-key concurrency -----------------------------------


@hyp_settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(size=st.integers(min_value=1, max_value=10))
def test_preserve_distinct_key_max_workers(patch_settings, size):
    """Preservation: a distinct-key batch sizes the pool at min(MAX_CONCURRENT_DOCUMENTS, n).

    Covers size boundaries around MAX_CONCURRENT_DOCUMENTS (fixed at 4 here) and
    single-job batches.

    Validates: Requirements 3.1
    """
    patch_settings.MAX_CONCURRENT_DOCUMENTS = 4
    jobs = _distinct_key_batch(size)
    _assert_distinct_source_doc_ids(jobs)

    pipeline = mock.Mock()
    pipeline.process_document.return_value = None
    source = _RecordingSource()

    captured_max_workers: list[int] = []
    real_executor = ThreadPoolExecutor

    def _recording_executor(max_workers, *args, **kwargs):
        captured_max_workers.append(max_workers)
        return real_executor(max_workers=max_workers, *args, **kwargs)

    with mock.patch(
        "ingestion_pipeline.orchestration.batch_processing.batch_runner.ThreadPoolExecutor",
        side_effect=_recording_executor,
    ):
        results = run_batch(jobs, pipeline, source, batch_number=1).results

    assert len(results) == size
    assert captured_max_workers == [min(4, size)]


# --- Preservation: success acknowledgement ------------------------------------


@hyp_settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(size=st.integers(min_value=1, max_value=8))
def test_preserve_distinct_key_success_acknowledged_once(patch_settings, size):
    """Preservation: each succeeding distinct-key job is acknowledged exactly once.

    Validates: Requirements 3.2
    """
    patch_settings.MAX_CONCURRENT_DOCUMENTS = 4
    jobs = _distinct_key_batch(size)
    _assert_distinct_source_doc_ids(jobs)

    pipeline = mock.Mock()
    pipeline.process_document.return_value = None
    source = _RecordingSource()

    results = run_batch(jobs, pipeline, source, batch_number=1).results

    assert len(results) == size
    assert all(r.success for r in results)
    # Each job acknowledged exactly once (order-independent).
    ack_counts = Counter(id(job) for job in source.acknowledged)
    assert ack_counts == Counter(id(job) for job in jobs)
    assert len(source.acknowledged) == size


# --- Preservation: failure classification / cleanup ---------------------------


@hyp_settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(size=st.integers(min_value=1, max_value=6), fail_index=st.integers(min_value=0, max_value=5))
def test_preserve_distinct_key_failure_unacknowledged_and_classified(patch_settings, size, fail_index):
    """Preservation: a failing distinct-key job is unacknowledged and classified.

    The failing job's DocumentResult carries success=False with category/retryable
    set; it is not acknowledged. Every other (succeeding) job is acknowledged.

    Validates: Requirements 3.3
    """
    patch_settings.MAX_CONCURRENT_DOCUMENTS = 4
    fail_index = fail_index % size
    jobs = _distinct_key_batch(size)
    _assert_distinct_source_doc_ids(jobs)

    failing_job = jobs[fail_index]
    failing_source_doc_id = _expected_source_doc_id(failing_job)

    pipeline = _RecordingPipeline(fail_source_doc_ids={failing_source_doc_id})
    source = _RecordingSource()

    results = run_batch(jobs, pipeline, source, batch_number=1).results

    assert len(results) == size

    failing_results = [r for r in results if r.source_doc_id == failing_source_doc_id]
    assert len(failing_results) == 1
    failing_result = failing_results[0]
    assert failing_result.success is False
    assert failing_result.category is DlqCategory.ZERO_CHUNKS_EXTRACTED_FROM_DOCUMENT
    assert failing_result.retryable is False

    # The failing job is left unacknowledged; the rest are acknowledged.
    acked_ids = {id(job) for job in source.acknowledged}
    assert id(failing_job) not in acked_ids
    for job in jobs:
        if job is not failing_job:
            assert id(job) in acked_ids
    assert len(source.acknowledged) == size - 1


# --- Preservation: one result per job, deterministic source_doc_id -------------


@hyp_settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(size=st.integers(min_value=1, max_value=10))
def test_preserve_distinct_key_one_result_per_job_with_stable_ids(patch_settings, size):
    """Preservation: one DocumentResult per job; source_doc_id matches the deterministic id.

    Validates: Requirements 3.1, 3.4
    """
    patch_settings.MAX_CONCURRENT_DOCUMENTS = 4
    jobs = _distinct_key_batch(size)
    _assert_distinct_source_doc_ids(jobs)

    pipeline = mock.Mock()
    pipeline.process_document.return_value = None
    source = _RecordingSource()

    results = run_batch(jobs, pipeline, source, batch_number=1).results

    # Exactly one result per job.
    assert len(results) == size
    result_jobs = {id(r.job) for r in results}
    assert result_jobs == {id(job) for job in jobs}

    # Each result's source_doc_id is the deterministic id for its job.
    for result in results:
        assert result.source_doc_id == _expected_source_doc_id(result.job)

    # All the deterministic ids are distinct (matches the distinct-key input).
    assert len({r.source_doc_id for r in results}) == size


# --- Preservation: empty batch ------------------------------------------------


def test_preserve_empty_batch_returns_empty_list():
    """Preservation: run_batch([], ...) == [] with no processing or acknowledgement.

    Validates: Requirements 3.5
    """
    pipeline = mock.Mock()
    source = _RecordingSource()

    results = run_batch([], pipeline, source, batch_number=1).results

    assert results == []
    pipeline.process_document.assert_not_called()
    assert source.acknowledged == []


# --- Preservation: distinct case_refs (broader natural-key coverage) ----------


@hyp_settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(case_refs=st.lists(_CASE_REF_STRATEGY, min_size=1, max_size=8, unique=True))
def test_preserve_distinct_case_refs_success_acknowledged_once(patch_settings, case_refs):
    """Preservation: distinct case_refs form distinct-key batches processed and acked once each.

    Broadens coverage beyond a single case_ref: each generated case_ref matches the
    CICA two-digit / 7-or-8 / five-digit pattern so the S3 URI validates, and
    uniqueness of case_refs guarantees distinct source_doc_ids.

    Validates: Requirements 3.1, 3.2, 3.4
    """
    patch_settings.MAX_CONCURRENT_DOCUMENTS = 4
    jobs = [_make_distinct_job(i, case_ref=case_ref) for i, case_ref in enumerate(case_refs)]
    _assert_distinct_source_doc_ids(jobs)

    pipeline = mock.Mock()
    pipeline.process_document.return_value = None
    source = _RecordingSource()

    results = run_batch(jobs, pipeline, source, batch_number=1).results

    assert len(results) == len(jobs)
    assert all(r.success for r in results)
    assert Counter(id(job) for job in source.acknowledged) == Counter(id(job) for job in jobs)
    for result in results:
        assert result.source_doc_id == _expected_source_doc_id(result.job)


# --- Task 4.1: Unit tests for compute_source_doc_id and run_batch --------------
#
# BUGFIX WORKFLOW — verification unit tests for spec `duplicate-source-key-dedup`.
#
# These complement the exploration tests (Task 1, test_explore_*) and the
# preservation property tests (Task 2, test_preserve_*) with focused, example-
# based assertions on the FIXED runner:
#   * compute_source_doc_id is the single source of truth for the natural-key ->
#     source_doc_id computation (matches DocumentIdentifier(...).generate_uuid()),
#   * run_batch grouping: one owner per source_doc_id, duplicate acknowledgement
#     follows the owner's outcome,
#   * duplicate-collapse observability logging (2.6),
#   * distinct-key result count / acknowledgement / worker sizing,
#   * empty batch.


# --- compute_source_doc_id ----------------------------------------------------


def test_compute_source_doc_id_matches_document_identifier():
    """compute_source_doc_id equals DocumentIdentifier(...).generate_uuid() for a job.

    Confirms the extracted helper is the single source of truth and did not change
    the deterministic computation.

    Validates: Requirements 3.4
    """
    job = _make_job()
    expected = DocumentIdentifier(
        source_file_name=job.source_file_name,
        correspondence_type=job.correspondence_type,
        case_ref=job.case_ref,
    ).generate_uuid()

    assert compute_source_doc_id(job) == expected


def test_compute_source_doc_id_equal_keys_collide():
    """Two jobs with the same natural key resolve to the same source_doc_id.

    Validates: Requirements 3.4
    """
    job_a = _make_dup_job()
    job_b = _make_dup_job()  # identical natural key

    assert compute_source_doc_id(job_a) == compute_source_doc_id(job_b)


def test_compute_source_doc_id_distinct_keys_do_not_collide():
    """Jobs with distinct natural keys resolve to distinct source_doc_ids.

    Validates: Requirements 3.4
    """
    jobs = _distinct_key_batch(5)

    ids = [compute_source_doc_id(job) for job in jobs]
    assert len(set(ids)) == len(ids)


def test_compute_source_doc_id_is_receipt_handle_independent():
    """source_doc_id depends only on the natural key, not the receipt handle.

    Two jobs with the same natural key but different SQS receipt handles (the SQS
    redelivery case) must still collide onto one source_doc_id.

    Validates: Requirements 3.4
    """
    job_a = _make_dup_job().model_copy(update={"receipt_handle": "handle-a"})
    job_b = _make_dup_job().model_copy(update={"receipt_handle": "handle-b"})

    assert compute_source_doc_id(job_a) == compute_source_doc_id(job_b)


# --- run_batch grouping: duplicate-key batch ----------------------------------


def test_run_batch_duplicate_key_submits_one_owner_per_source_doc_id():
    """A duplicate-key batch processes exactly one owner per source_doc_id.

    Three jobs share one natural key; the pipeline is invoked once and exactly one
    DocumentResult is produced for that id.

    Validates: Requirements 2.1, 2.2, 3.1
    """
    pipeline = _RecordingPipeline()
    source = _RecordingSource()
    jobs = [_make_dup_job() for _ in range(3)]
    source_doc_id = _expected_source_doc_id(jobs[0])

    results = run_batch(jobs, pipeline, source, batch_number=1).results

    assert pipeline.invocation_counts()[source_doc_id] == 1
    assert len(results) == 1
    assert results[0].source_doc_id == source_doc_id
    # The owner is the first job seen for the id (input order preserved).
    assert results[0].job is jobs[0]


def test_run_batch_duplicate_key_acknowledges_all_on_owner_success():
    """On owner success, the owner and every collapsed duplicate are acknowledged.

    Validates: Requirements 2.5, 3.2
    """
    pipeline = _RecordingPipeline()
    source = _RecordingSource()
    jobs = [_make_dup_job() for _ in range(3)]

    run_batch(jobs, pipeline, source, batch_number=1)

    acked_ids = Counter(id(job) for job in source.acknowledged)
    # Every input job (owner + duplicates) acknowledged exactly once.
    assert acked_ids == Counter(id(job) for job in jobs)
    assert len(source.acknowledged) == 3


def test_run_batch_duplicate_key_leaves_all_unacknowledged_on_owner_failure():
    """On owner failure, the owner and its duplicates are left unacknowledged.

    They are redriven together; none is silently dropped.

    Validates: Requirements 2.5, 3.3
    """
    jobs = [_make_dup_job() for _ in range(3)]
    source_doc_id = _expected_source_doc_id(jobs[0])
    pipeline = _RecordingPipeline(fail_source_doc_ids={source_doc_id})
    source = _RecordingSource()

    results = run_batch(jobs, pipeline, source, batch_number=1).results

    # One owner result, failed; nothing acknowledged.
    assert len(results) == 1
    assert results[0].success is False
    assert results[0].category is DlqCategory.ZERO_CHUNKS_EXTRACTED_FROM_DOCUMENT
    assert source.acknowledged == []


# --- run_batch grouping: mixed duplicate + distinct keys ----------------------


def test_run_batch_mixed_keys_one_owner_per_distinct_id():
    """A mixed batch collapses duplicates while processing distinct keys normally.

    Batch: [dupA, distinct0, dupA, distinct1, dupA] -> owners = {dupA, distinct0,
    distinct1}. The pipeline is invoked once per distinct id, and every input job
    is acknowledged on success.

    Validates: Requirements 2.1, 2.2, 2.5, 3.1, 3.2
    """
    dup_a1 = _make_dup_job()
    dup_a2 = _make_dup_job()
    dup_a3 = _make_dup_job()
    distinct_0 = _make_distinct_job(0)
    distinct_1 = _make_distinct_job(1)
    jobs = [dup_a1, distinct_0, dup_a2, distinct_1, dup_a3]

    dup_id = _expected_source_doc_id(dup_a1)
    pipeline = _RecordingPipeline()
    source = _RecordingSource()

    results = run_batch(jobs, pipeline, source, batch_number=1).results

    # Three distinct source_doc_ids -> three owner results.
    assert len(results) == 3
    assert {r.source_doc_id for r in results} == {
        dup_id,
        _expected_source_doc_id(distinct_0),
        _expected_source_doc_id(distinct_1),
    }
    # The duplicate id is processed exactly once (dup_a1 is the owner).
    assert pipeline.invocation_counts()[dup_id] == 1
    owner_result = next(r for r in results if r.source_doc_id == dup_id)
    assert owner_result.job is dup_a1
    # Every input job acknowledged exactly once on success.
    assert Counter(id(job) for job in source.acknowledged) == Counter(id(job) for job in jobs)


# --- run_batch distinct-key batch (example-based) -----------------------------


def test_run_batch_distinct_key_one_result_per_job_and_acked(patch_settings):
    """A distinct-key batch yields one DocumentResult per job, each acknowledged.

    Validates: Requirements 3.1, 3.2
    """
    patch_settings.MAX_CONCURRENT_DOCUMENTS = 4
    jobs = _distinct_key_batch(3)
    pipeline = mock.Mock()
    pipeline.process_document.return_value = None
    source = _RecordingSource()

    results = run_batch(jobs, pipeline, source, batch_number=1).results

    assert len(results) == 3
    assert all(r.success for r in results)
    assert {id(r.job) for r in results} == {id(job) for job in jobs}
    assert Counter(id(job) for job in source.acknowledged) == Counter(id(job) for job in jobs)


def test_run_batch_distinct_key_failure_unacknowledged(patch_settings):
    """A failing distinct-key job is left unacknowledged; the rest are acknowledged.

    Validates: Requirements 3.2, 3.3
    """
    patch_settings.MAX_CONCURRENT_DOCUMENTS = 4
    jobs = _distinct_key_batch(3)
    failing_job = jobs[1]
    failing_id = _expected_source_doc_id(failing_job)
    pipeline = _RecordingPipeline(fail_source_doc_ids={failing_id})
    source = _RecordingSource()

    results = run_batch(jobs, pipeline, source, batch_number=1).results

    assert len(results) == 3
    failing_result = next(r for r in results if r.source_doc_id == failing_id)
    assert failing_result.success is False
    assert failing_result.retryable is False
    acked_ids = {id(job) for job in source.acknowledged}
    assert id(failing_job) not in acked_ids
    assert len(source.acknowledged) == 2


@pytest.mark.parametrize(
    ("limit", "n", "expected_workers"),
    [
        (4, 2, 2),  # fewer jobs than the limit -> capped at job count
        (4, 4, 4),  # equal -> the limit
        (3, 10, 3),  # more jobs than the limit -> capped at the limit
    ],
)
def test_run_batch_distinct_key_max_workers(patch_settings, limit, n, expected_workers):
    """A distinct-key batch sizes the pool at min(MAX_CONCURRENT_DOCUMENTS, n).

    n here is the number of owners, which equals the job count for a distinct-key
    batch.

    Validates: Requirements 3.1
    """
    patch_settings.MAX_CONCURRENT_DOCUMENTS = limit
    jobs = _distinct_key_batch(n)
    pipeline = mock.Mock()
    pipeline.process_document.return_value = None
    source = _RecordingSource()

    captured_max_workers: list[int] = []
    real_executor = ThreadPoolExecutor

    def _recording_executor(max_workers, *args, **kwargs):
        captured_max_workers.append(max_workers)
        return real_executor(max_workers=max_workers, *args, **kwargs)

    with mock.patch(
        "ingestion_pipeline.orchestration.batch_processing.batch_runner.ThreadPoolExecutor",
        side_effect=_recording_executor,
    ):
        run_batch(jobs, pipeline, source, batch_number=1)

    assert captured_max_workers == [expected_workers]


def test_run_batch_duplicate_key_max_workers_counts_owners_not_jobs(patch_settings):
    """max_workers is sized by the owner count, not the raw job count.

    A batch of 6 jobs that collapse to 2 distinct owners sizes the pool at
    min(MAX_CONCURRENT_DOCUMENTS, 2), not min(limit, 6).

    Validates: Requirements 2.1, 3.1
    """
    patch_settings.MAX_CONCURRENT_DOCUMENTS = 4
    # Two distinct keys, each repeated three times -> 2 owners, 6 jobs.
    jobs = [
        _make_dup_job(file_name="a.pdf"),
        _make_dup_job(file_name="b.pdf"),
        _make_dup_job(file_name="a.pdf"),
        _make_dup_job(file_name="b.pdf"),
        _make_dup_job(file_name="a.pdf"),
        _make_dup_job(file_name="b.pdf"),
    ]
    pipeline = mock.Mock()
    pipeline.process_document.return_value = None
    source = _RecordingSource()

    captured_max_workers: list[int] = []
    real_executor = ThreadPoolExecutor

    def _recording_executor(max_workers, *args, **kwargs):
        captured_max_workers.append(max_workers)
        return real_executor(max_workers=max_workers, *args, **kwargs)

    with mock.patch(
        "ingestion_pipeline.orchestration.batch_processing.batch_runner.ThreadPoolExecutor",
        side_effect=_recording_executor,
    ):
        results = run_batch(jobs, pipeline, source, batch_number=1).results

    # min(4, 2 owners) == 2.
    assert captured_max_workers == [2]
    assert len(results) == 2


# --- run_batch duplicate-collapse observability logging (2.6) -----------------


def test_run_batch_duplicate_collapse_logs_structured_entry(caplog):
    """A duplicate-keyed batch emits a collapse log naming id, count, and URIs/case_ref.

    Validates: Requirements 2.6
    """
    pipeline = _RecordingPipeline()
    source = _RecordingSource()
    dup_1 = _make_dup_job(case_ref="26-711111", file_name="dup.pdf")
    dup_2 = _make_dup_job(case_ref="26-711111", file_name="dup.pdf")
    dup_3 = _make_dup_job(case_ref="26-711111", file_name="dup.pdf")
    source_doc_id = _expected_source_doc_id(dup_1)

    with caplog.at_level(logging.WARNING, logger="ingestion_pipeline.orchestration.batch_processing.batch_runner"):
        run_batch([dup_1, dup_2, dup_3], pipeline, source, batch_number=1)

    collapse_records = [
        record
        for record in caplog.records
        if "duplicate" in record.getMessage().lower() and source_doc_id in record.getMessage()
    ]
    assert collapse_records, "expected a duplicate-collapse log entry naming the source_doc_id"
    message = collapse_records[-1].getMessage()
    # Names the count of collapsed duplicates (2 duplicates behind one owner).
    assert "2" in message
    # Names the duplicate jobs' S3 URI / case_ref where available.
    assert dup_2.source_file_s3_uri in message
    assert dup_2.case_ref in message


def test_run_batch_distinct_key_emits_no_collapse_log(caplog):
    """A distinct-key batch emits no duplicate-collapse log entry.

    Validates: Requirements 2.6
    """
    pipeline = mock.Mock()
    pipeline.process_document.return_value = None
    source = _RecordingSource()
    jobs = _distinct_key_batch(3)

    with caplog.at_level(logging.WARNING, logger="ingestion_pipeline.orchestration.batch_processing.batch_runner"):
        run_batch(jobs, pipeline, source, batch_number=1)

    collapse_records = [record for record in caplog.records if "collapsed" in record.getMessage().lower()]
    assert collapse_records == []


# --- run_batch empty batch ----------------------------------------------------


def test_run_batch_empty_returns_empty_list_no_side_effects():
    """An empty batch returns [] with no processing and no acknowledgement.

    Validates: Requirements 3.5
    """
    pipeline = _RecordingPipeline()
    source = _RecordingSource()

    results = run_batch([], pipeline, source, batch_number=1).results

    assert results == []
    assert pipeline.invocations == []
    assert source.acknowledged == []


# --- Task 4.2: Property-based tests (hypothesis) ------------------------------
#
# BUGFIX WORKFLOW — verification property tests for spec `duplicate-source-key-dedup`.
#
# These verify the FIXED runner against the correctness properties over generated
# inputs (complementing the scoped exploration PBT and the preservation PBTs):
#   * Property 1 (Fix Checking) over MIXED duplicate+distinct batches,
#   * Property 2 (Preservation) — fixed observable outcome matches the original for
#     distinct-key batches,
#   * same-key-repeated-N-times: one owner processed, N-1 duplicates acked on success.


def _mixed_key_batch(distinct_count: int, dup_group_sizes: list[int]) -> list[DocumentJob]:
    """Build a batch mixing distinct-key jobs with duplicate groups, order-interleaved.

    Each entry in dup_group_sizes creates a group of that many jobs sharing one
    natural key (>=2 => that group is a genuine duplicate group). Distinct jobs use
    unique file names so their ids never collide with each other or the dup groups.
    """
    jobs: list[DocumentJob] = []
    for i in range(distinct_count):
        jobs.append(_make_distinct_job(i))
    for group_index, size in enumerate(dup_group_sizes):
        for _ in range(size):
            jobs.append(_make_dup_job(file_name=f"dupgroup_{group_index}.pdf"))
    # Interleave so owners and duplicates are not contiguous (exercises ordering).
    jobs.sort(key=lambda job: job.source_file_name)
    return jobs


@hyp_settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    distinct_count=st.integers(min_value=0, max_value=4),
    dup_group_sizes=st.lists(st.integers(min_value=2, max_value=4), min_size=1, max_size=3),
)
def test_property_mixed_keys_each_id_processed_once_with_defined_outcome(
    patch_settings, distinct_count, dup_group_sizes
):
    """Property 1: mixed batches process each source_doc_id once; every job has an outcome.

    Generates batches mixing duplicate and distinct keys and asserts each distinct
    source_doc_id is handed to the pipeline at most once, no two units overlap, and
    every input job reaches a defined acknowledgement outcome (all owners succeed
    here, so every job is acknowledged).

    Validates: Requirements 2.1, 2.2, 2.3, 2.5
    """
    patch_settings.MAX_CONCURRENT_DOCUMENTS = 4
    jobs = _mixed_key_batch(distinct_count, dup_group_sizes)
    pipeline = _RecordingPipeline(sleep_seconds=0.01)
    source = _RecordingSource()

    results = run_batch(jobs, pipeline, source, batch_number=1).results

    distinct_ids = {_expected_source_doc_id(job) for job in jobs}
    # One owner result per distinct source_doc_id.
    assert {r.source_doc_id for r in results} == distinct_ids
    assert len(results) == len(distinct_ids)

    # Each distinct id handed to the pipeline at most once, and none overlap.
    counts = pipeline.invocation_counts()
    for source_doc_id in distinct_ids:
        assert counts[source_doc_id] <= 1
    assert not pipeline.any_same_id_overlap()

    # Every input job reaches a defined acknowledgement outcome (owners succeeded).
    for job in jobs:
        assert _acknowledgement_outcome_defined(job, source, owner_succeeded=True)
    assert Counter(id(job) for job in source.acknowledged) == Counter(id(job) for job in jobs)


@hyp_settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(size=st.integers(min_value=0, max_value=10))
def test_property_distinct_key_fixed_matches_original_observable_outcome(patch_settings, size):
    """Property 2: for distinct-key batches the fixed runner matches the original.

    The original (unfixed) behaviour for a distinct-key batch is: one result per
    job, every job acknowledged exactly once on success, source_doc_id equal to the
    deterministic id. Since grouping is a no-op for distinct keys, the fixed runner
    must reproduce exactly that observable outcome across sizes (including the empty
    batch and boundaries around MAX_CONCURRENT_DOCUMENTS).

    Validates: Requirements 3.1, 3.2, 3.4, 3.5
    """
    patch_settings.MAX_CONCURRENT_DOCUMENTS = 4
    jobs = _distinct_key_batch(size)
    _assert_distinct_source_doc_ids(jobs)

    pipeline = mock.Mock()
    pipeline.process_document.return_value = None
    source = _RecordingSource()

    results = run_batch(jobs, pipeline, source, batch_number=1).results

    # One result per job (empty batch -> []).
    assert len(results) == size
    assert {id(r.job) for r in results} == {id(job) for job in jobs}
    assert all(r.success for r in results)
    for result in results:
        assert result.source_doc_id == _expected_source_doc_id(result.job)
    # Every job acknowledged exactly once (order-independent).
    assert Counter(id(job) for job in source.acknowledged) == Counter(id(job) for job in jobs)


@hyp_settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    n=st.integers(min_value=2, max_value=6),
    case_ref=st.sampled_from(["26-711111", "27-800001", "26-700030"]),
    file_name=st.sampled_from(["dup.pdf", "case30.pdf", "brain_injury.pdf"]),
)
def test_property_same_key_repeated_one_owner_n_minus_1_dropped(patch_settings, n, case_ref, file_name):
    """Property 1: a key repeated N times -> one owner processed, N-1 duplicates acked.

    On owner success, exactly one owner is processed for the shared source_doc_id
    and all N jobs (owner + N-1 duplicates) are acknowledged.

    Validates: Requirements 2.1, 2.5, 3.2
    """
    patch_settings.MAX_CONCURRENT_DOCUMENTS = 4
    jobs = [_make_dup_job(case_ref=case_ref, file_name=file_name) for _ in range(n)]
    source_doc_id = _expected_source_doc_id(jobs[0])
    assert len({_expected_source_doc_id(j) for j in jobs}) == 1  # bug condition

    pipeline = _RecordingPipeline()
    source = _RecordingSource()

    results = run_batch(jobs, pipeline, source, batch_number=1).results

    # Exactly one owner processed.
    assert len(results) == 1
    assert results[0].source_doc_id == source_doc_id
    assert pipeline.invocation_counts()[source_doc_id] == 1
    # All N jobs acknowledged (1 owner + N-1 duplicates dropped).
    assert len(source.acknowledged) == n
    assert Counter(id(job) for job in source.acknowledged) == Counter(id(job) for job in jobs)


# --- Task 4.3: Integration tests with a fake pipeline + recording DocumentSource
#
# BUGFIX WORKFLOW — end-to-end integration tests for spec `duplicate-source-key-dedup`.
#
# These drive the full run_batch flow with a fake pipeline that records the S3
# page-image prefix and OpenSearch document-id ownership derived from
# source_doc_id, plus a recording DocumentSource. Duplicate jobs carry distinct
# receipt handles (the SQS redelivery shape) so acknowledgement of every handle is
# observable.


class _OwnershipPipeline:
    """Fake pipeline that records ownership of the shared deterministic identifiers.

    For each processed document it records the S3 page-image prefix
    (`{case_ref}/{source_doc_id}/pages/`) and the OpenSearch document-id namespace
    (keyed by source_doc_id) it "wrote", so a test can assert that exactly one unit
    ever owns those shared resources per source_doc_id. A configurable failure set
    raises a classified PipelineError; on failure the fake records a cleanup keyed
    by source_doc_id (mirroring _cleanup_document, which deletes by source_doc_id /
    case_ref).
    """

    def __init__(self, fail_source_doc_ids: set[str] | None = None) -> None:
        self.fail_source_doc_ids = fail_source_doc_ids or set()
        self._lock = threading.Lock()
        self.s3_prefix_writes: list[str] = []
        self.opensearch_id_writes: list[str] = []
        self.cleanups: list[str] = []

    def process_document(self, document_metadata: DocumentMetadata) -> None:
        source_doc_id = document_metadata.source_doc_id
        s3_prefix = f"{document_metadata.case_ref}/{source_doc_id}/pages/"
        with self._lock:
            self.s3_prefix_writes.append(s3_prefix)
            self.opensearch_id_writes.append(source_doc_id)
        if source_doc_id in self.fail_source_doc_ids:
            with self._lock:
                # Cleanup is keyed solely by source_doc_id / case_ref.
                self.cleanups.append(source_doc_id)
            raise EmptyTextractResponseError(
                "forced failure",
                source_doc_id=source_doc_id,
                case_ref=document_metadata.case_ref,
                s3_uri=document_metadata.source_file_s3_uri,
            )


def _make_dup_job_with_handle(handle: str, case_ref: str = "26-711111", file_name: str = "dup.pdf") -> DocumentJob:
    """A duplicate-keyed job carrying a distinct SQS receipt handle."""
    return DocumentJob(
        source_file_s3_uri=f"s3://{_DUP_BUCKET}/{case_ref}/{file_name}",
        correspondence_type="TC19 - ADDITIONAL INFO REQUEST",
        case_ref=case_ref,
        receipt_handle=handle,
    )


def test_integration_duplicate_batch_single_ownership_and_all_handles_acked(patch_settings):
    """Integration: a duplicate-keyed batch processes once and acks all handles on success.

    Three jobs share a natural key but carry distinct receipt handles (SQS
    redelivery). The fake pipeline must write the shared S3 prefix and OpenSearch id
    exactly once (single ownership), and the recording source must acknowledge all
    three handles.

    Validates: Requirements 2.1, 2.2, 2.5, 3.2
    """
    patch_settings.MAX_CONCURRENT_DOCUMENTS = 4
    jobs = [_make_dup_job_with_handle(f"handle-{i}") for i in range(3)]
    source_doc_id = _expected_source_doc_id(jobs[0])
    expected_prefix = f"26-711111/{source_doc_id}/pages/"

    pipeline = _OwnershipPipeline()
    source = _RecordingSource()

    results = run_batch(jobs, pipeline, source, batch_number=1).results

    # Single processing / single ownership of the shared identifiers.
    assert len(results) == 1
    assert pipeline.s3_prefix_writes == [expected_prefix]
    assert pipeline.opensearch_id_writes == [source_doc_id]
    # All duplicate receipt handles acknowledged.
    assert {job.receipt_handle for job in source.acknowledged} == {"handle-0", "handle-1", "handle-2"}
    assert len(source.acknowledged) == 3


def test_integration_duplicate_batch_failing_owner_leaves_all_for_redrive(patch_settings):
    """Integration: a failing owner leaves owner and duplicates unacknowledged; cleanup is isolated.

    Validates: Requirements 2.3, 2.5, 3.3
    """
    patch_settings.MAX_CONCURRENT_DOCUMENTS = 4
    jobs = [_make_dup_job_with_handle(f"handle-{i}") for i in range(3)]
    source_doc_id = _expected_source_doc_id(jobs[0])

    pipeline = _OwnershipPipeline(fail_source_doc_ids={source_doc_id})
    source = _RecordingSource()

    results = run_batch(jobs, pipeline, source, batch_number=1).results

    # One owner processed and failed; nothing acknowledged (all left for redrive).
    assert len(results) == 1
    assert results[0].success is False
    assert results[0].category is DlqCategory.EMPTY_TEXTRACT_RESPONSE
    assert source.acknowledged == []
    # The shared id was written by exactly one unit, and cleanup affects only that
    # single de-duplicated unit (one cleanup for one source_doc_id).
    assert pipeline.opensearch_id_writes == [source_doc_id]
    assert pipeline.cleanups == [source_doc_id]


def test_integration_distinct_batch_matches_prefix_baseline(patch_settings):
    """Integration: a distinct-key batch behaves identically to the pre-fix baseline.

    Every job is processed (distinct S3 prefixes / OpenSearch ids), every job is
    acknowledged exactly once, and the failing job is classified and left
    unacknowledged. Grouping is a no-op for distinct keys.

    Validates: Requirements 3.1, 3.2, 3.3
    """
    patch_settings.MAX_CONCURRENT_DOCUMENTS = 4
    jobs = [_make_dup_job_with_handle(f"handle-{i}", file_name=f"distinct_{i}.pdf") for i in range(4)]
    _assert_distinct_source_doc_ids(jobs)
    failing_job = jobs[2]
    failing_id = _expected_source_doc_id(failing_job)

    pipeline = _OwnershipPipeline(fail_source_doc_ids={failing_id})
    source = _RecordingSource()

    results = run_batch(jobs, pipeline, source, batch_number=1).results

    # One result per job; distinct ownership of each id / prefix.
    assert len(results) == 4
    assert len(set(pipeline.opensearch_id_writes)) == 4
    assert len(set(pipeline.s3_prefix_writes)) == 4

    # The failing job is classified and left unacknowledged; the rest are acked once.
    failing_result = next(r for r in results if r.source_doc_id == failing_id)
    assert failing_result.success is False
    assert failing_result.category is DlqCategory.EMPTY_TEXTRACT_RESPONSE
    acked_handles = {job.receipt_handle for job in source.acknowledged}
    assert failing_job.receipt_handle not in acked_handles
    assert acked_handles == {"handle-0", "handle-1", "handle-3"}
    assert len(source.acknowledged) == 3


@hyp_settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(n=st.integers(min_value=2, max_value=6))
def test_property_same_key_distinct_handles_each_acked_once(patch_settings, n):
    """Property 1: duplicates with distinct receipt handles are each acknowledged once.

    N jobs share one natural key (the bug condition) but carry distinct SQS receipt
    handles (the redelivery shape). On owner success every message must be
    acknowledged by its own handle exactly once — distinguishing duplicates by a
    real field, not Python object identity. Guards against a regression that acks a
    single job repeatedly (or conflates duplicates by value equality) rather than
    acking each distinct message.

    Validates: Requirements 2.1, 2.5, 3.2
    """
    patch_settings.MAX_CONCURRENT_DOCUMENTS = 4
    jobs = [_make_dup_job_with_handle(f"handle-{i}") for i in range(n)]
    assert len({_expected_source_doc_id(j) for j in jobs}) == 1  # bug condition

    pipeline = _RecordingPipeline()
    source = _RecordingSource()

    run_batch(jobs, pipeline, source, batch_number=1)

    acked_handles = [job.receipt_handle for job in source.acknowledged]
    # Each distinct message acknowledged exactly once (owner + N-1 duplicates).
    assert sorted(acked_handles) == sorted(f"handle-{i}" for i in range(n))
    assert len(set(acked_handles)) == n


# --- run-and-batch-summaries (task 3.2): BatchResult summary + logging contract
#
# These cover the structured batch-summary added by task 3.1:
#   * exactly one batch-summary record per batch, no legacy "Batch complete" line,
#     with the five counts in both the message and the logging `extra` (Req 3.1, 3.4),
#   * BatchSummary counts for a distinct-key batch and for a duplicate-collapsing
#     batch (Req 2.1, 2.2, 2.6, 2.7, 2.8, 2.9).

_BATCH_SUMMARY_LOGGER = "ingestion_pipeline.orchestration.batch_processing.batch_runner"


def _batch_summary_records(caplog):
    """Return INFO records that look like the structured batch-summary line."""
    return [
        record
        for record in caplog.records
        if record.levelno == logging.INFO
        and record.getMessage().startswith("Batch ")
        and "summary:" in record.getMessage()
    ]


def test_run_batch_emits_single_structured_summary_record(caplog):
    """A completed batch emits exactly one structured batch-summary record.

    The record renders the five counts into the message AND attaches them via
    `extra`; the legacy "Batch complete" line is gone.

    Validates: Requirements 3.1, 3.4
    """
    pipeline = mock.Mock()
    pipeline.process_document.return_value = None
    source = mock.Mock()

    good = _make_job()
    bad = _make_job(s3_uri="s3://test-kta-documents-bucket/bad/file.pdf", case_ref="bad")

    with caplog.at_level(logging.INFO, logger=_BATCH_SUMMARY_LOGGER):
        result = run_batch([good, bad], pipeline, source, batch_number=2)

    # Exactly one structured batch-summary record.
    summary_records = _batch_summary_records(caplog)
    assert len(summary_records) == 1
    record = summary_records[0]

    # No legacy "Batch complete" line survives (Req 3.4).
    assert not any("Batch complete" in r.getMessage() for r in caplog.records)

    # The five counts are attached via `extra` with the correct values.
    assert record.batch_number == 2
    assert record.jobs_in_batch == 2
    assert record.succeeded == 1
    assert record.failed == 1
    assert record.duplicates_collapsed == 0

    # And they are rendered into the human-readable message.
    message = record.getMessage()
    assert "Batch 2 summary" in message
    assert "2 job(s) in batch" in message
    assert "1 succeeded" in message
    assert "1 failed" in message
    assert "0 duplicate(s) collapsed" in message

    # The returned summary carries the same values.
    assert result.summary.batch_number == 2
    assert result.summary.jobs_in_batch == 2
    assert result.summary.succeeded == 1
    assert result.summary.failed == 1
    assert result.summary.duplicates_collapsed == 0


def test_run_batch_summary_counts_for_distinct_key_batch():
    """A distinct-key batch reports jobs_in_batch == succeeded and no duplicates.

    Validates: Requirements 2.2, 2.6, 2.7, 2.9
    """
    pipeline = mock.Mock()
    pipeline.process_document.return_value = None
    source = _RecordingSource()

    jobs = _distinct_key_batch(3)

    result = run_batch(jobs, pipeline, source, batch_number=1)

    assert result.summary.jobs_in_batch == 3
    assert result.summary.succeeded == 3
    assert result.summary.failed == 0
    assert result.summary.duplicates_collapsed == 0
    assert len(result.results) == 3


def test_run_batch_summary_counts_collapsed_duplicates():
    """Three jobs sharing one owner report jobs_in_batch=3 with two duplicates collapsed.

    The three jobs collapse onto a single owner, so succeeded + failed == 1 (one
    owner result) and duplicates_collapsed == 2.

    Validates: Requirements 2.6, 2.8, 2.9
    """
    pipeline = _RecordingPipeline()
    source = _RecordingSource()

    jobs = [_make_dup_job() for _ in range(3)]

    result = run_batch(jobs, pipeline, source, batch_number=1)

    assert result.summary.jobs_in_batch == 3
    assert result.summary.succeeded + result.summary.failed == 1
    assert result.summary.duplicates_collapsed == 2
    assert len(result.results) == 1
