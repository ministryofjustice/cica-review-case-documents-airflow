"""Tests for case_discovery.py."""

from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from evaluation_suite.search_evaluation.multi_case.case_discovery import (
    EVALUATION_CASE_PREFIX,
    CaseSpec,
    discover_cases,
)

MOCK_BUCKET = "test-source-bucket"
MOCK_REGION = "eu-west-2"


def _make_mock_s3(cases: list[tuple[str, str]]) -> boto3.client:
    """Create a moto-managed S3 client pre-populated with (case_ref, filename) pairs."""
    s3 = boto3.client("s3", region_name=MOCK_REGION)
    s3.create_bucket(
        Bucket=MOCK_BUCKET,
        CreateBucketConfiguration={"LocationConstraint": MOCK_REGION},
    )
    for case_ref, filename in cases:
        s3.put_object(Bucket=MOCK_BUCKET, Key=f"{case_ref}/{filename}", Body=b"")
    return s3


@mock_aws
@patch("evaluation_suite.search_evaluation.multi_case.case_discovery._get_s3_client")
def test_discover_cases_returns_sorted_case_specs(mock_get_client):
    """discover_cases returns CaseSpec objects sorted by case_ref."""
    mock_get_client.return_value = _make_mock_s3(
        [
            ("26-700003", "Case3_TC19_Redacted_White.pdf"),
            ("26-700001", "Case1_TC19_50_pages_brain_injury.pdf"),
            ("26-700002", "Case2_TC19_Redacted_White.pdf"),
        ]
    )

    results = discover_cases(bucket=MOCK_BUCKET)

    assert results == [
        CaseSpec("26-700001", "Case1_TC19_50_pages_brain_injury.pdf"),
        CaseSpec("26-700002", "Case2_TC19_Redacted_White.pdf"),
        CaseSpec("26-700003", "Case3_TC19_Redacted_White.pdf"),
    ]


@mock_aws
@patch("evaluation_suite.search_evaluation.multi_case.case_discovery._get_s3_client")
def test_discover_cases_excludes_non_pdf_objects(mock_get_client):
    """Non-PDF objects (metadata files, etc.) in a case folder are ignored."""
    s3 = _make_mock_s3([("26-700001", "Case1_TC19_50_pages_brain_injury.pdf")])
    s3.put_object(Bucket=MOCK_BUCKET, Key="26-700001/metadata.json", Body=b"{}")
    s3.put_object(Bucket=MOCK_BUCKET, Key="26-700001/thumbnail.png", Body=b"")
    mock_get_client.return_value = s3

    results = discover_cases(bucket=MOCK_BUCKET)

    assert len(results) == 1
    assert results[0].s3_filename == "Case1_TC19_50_pages_brain_injury.pdf"


@mock_aws
@patch("evaluation_suite.search_evaluation.multi_case.case_discovery._get_s3_client")
def test_discover_cases_scopes_to_prefix(mock_get_client):
    """Only case folders matching the prefix are returned; test fixtures are excluded."""
    mock_get_client.return_value = _make_mock_s3(
        [
            ("26-700001", "Case1_TC19_50_pages_brain_injury.pdf"),
            ("26-711111", "Case1_TC19_50_pages_brain_injury.pdf"),  # test fixture
            ("26-731111", "Case_3_TC19_Redacted_White.pdf"),  # test fixture
        ]
    )

    results = discover_cases(bucket=MOCK_BUCKET, prefix="26-700")

    assert len(results) == 1
    assert results[0].case_ref == "26-700001"


@mock_aws
@patch("evaluation_suite.search_evaluation.multi_case.case_discovery._get_s3_client")
def test_discover_cases_returns_empty_list_when_no_matches(mock_get_client):
    """discover_cases returns an empty list when no PDFs match the prefix."""
    mock_get_client.return_value = _make_mock_s3([])

    results = discover_cases(bucket=MOCK_BUCKET)

    assert results == []


@mock_aws
@patch("evaluation_suite.search_evaluation.multi_case.case_discovery._get_s3_client")
def test_discover_cases_takes_first_pdf_when_multiple_exist(mock_get_client):
    """When a case folder has multiple PDFs, the first in lexicographic order is used."""
    s3 = _make_mock_s3([])
    s3.create_bucket(
        Bucket=MOCK_BUCKET,
        CreateBucketConfiguration={"LocationConstraint": MOCK_REGION},
    ) if False else None  # already created by _make_mock_s3
    s3.put_object(Bucket=MOCK_BUCKET, Key="26-700001/B_second.pdf", Body=b"")
    s3.put_object(Bucket=MOCK_BUCKET, Key="26-700001/A_first.pdf", Body=b"")
    mock_get_client.return_value = s3

    results = discover_cases(bucket=MOCK_BUCKET)

    assert len(results) == 1
    assert results[0].case_ref == "26-700001"
    assert results[0].s3_filename == "A_first.pdf"


@mock_aws
@patch("evaluation_suite.search_evaluation.multi_case.case_discovery._get_s3_client")
def test_discover_cases_handles_paginated_results(mock_get_client):
    """discover_cases correctly accumulates results across multiple S3 pages."""
    cases = [(f"26-7000{i:02d}", f"Case{i}.pdf") for i in range(1, 31)]
    mock_get_client.return_value = _make_mock_s3(cases)

    results = discover_cases(bucket=MOCK_BUCKET)

    assert len(results) == 30
    assert results[0].case_ref == "26-700001"
    assert results[-1].case_ref == "26-700030"


def test_evaluation_case_prefix_targets_dev_uat_cases():
    """EVALUATION_CASE_PREFIX is set to scope discovery to dev/UAT evaluation cases."""
    assert EVALUATION_CASE_PREFIX == "26-700"


def test_case_spec_is_immutable():
    """CaseSpec is a frozen dataclass — attributes cannot be mutated."""
    spec = CaseSpec(case_ref="26-700001", s3_filename="Case1.pdf")
    with pytest.raises((AttributeError, TypeError)):
        spec.case_ref = "26-700002"  # type: ignore[misc]
