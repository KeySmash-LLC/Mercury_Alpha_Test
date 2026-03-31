"""Tests for scripts/analytics.py — distinct_id resolution and persistence."""
import os
import uuid
import pytest
from pathlib import Path
from unittest.mock import patch

from analytics import get_or_create_distinct_id, inject_pipeline_session_id, compute_cost_per_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolate_env():
    """Remove POSTHOG_DISTINCT_ID from os.environ before and after every test."""
    os.environ.pop("POSTHOG_DISTINCT_ID", None)
    yield
    os.environ.pop("POSTHOG_DISTINCT_ID", None)


# ---------------------------------------------------------------------------
# Returning an existing value
# ---------------------------------------------------------------------------

def test_returns_existing_env_var_without_touching_file(tmp_path):
    """When env var is already set, return it immediately and leave the file alone."""
    env_file = tmp_path / ".env"
    os.environ["POSTHOG_DISTINCT_ID"] = "my-existing-id"

    result = get_or_create_distinct_id(env_path=env_file)

    assert result == "my-existing-id"
    assert not env_file.exists()


def test_strips_whitespace_from_existing_env_var(tmp_path):
    """Whitespace around the env var value is ignored."""
    os.environ["POSTHOG_DISTINCT_ID"] = "  padded-id  "
    result = get_or_create_distinct_id(env_path=tmp_path / ".env")
    assert result == "padded-id"


def test_empty_env_var_triggers_generation(tmp_path):
    """An empty string env var is treated as absent and triggers generation."""
    os.environ["POSTHOG_DISTINCT_ID"] = ""
    env_file = tmp_path / ".env"
    env_file.write_text("POSTHOG_DISTINCT_ID=\n")

    result = get_or_create_distinct_id(env_path=env_file)

    assert result  # non-empty
    assert result != ""


# ---------------------------------------------------------------------------
# .env file handling — key exists but empty
# ---------------------------------------------------------------------------

def test_replaces_empty_key_in_existing_file(tmp_path):
    """Fills in an empty POSTHOG_DISTINCT_ID= line in an existing .env."""
    env_file = tmp_path / ".env"
    env_file.write_text("POSTHOG_API_KEY=abc\nPOSTHOG_DISTINCT_ID=\nOTHER=val\n")

    result = get_or_create_distinct_id(env_path=env_file)

    content = env_file.read_text()
    assert f"POSTHOG_DISTINCT_ID={result}" in content
    # Other keys must be preserved
    assert "POSTHOG_API_KEY=abc" in content
    assert "OTHER=val" in content
    # The empty placeholder must be gone
    assert "POSTHOG_DISTINCT_ID=\n" not in content


def test_does_not_duplicate_key_when_replacing(tmp_path):
    """Replacing an empty key does not produce two POSTHOG_DISTINCT_ID lines."""
    env_file = tmp_path / ".env"
    env_file.write_text("POSTHOG_DISTINCT_ID=\n")

    get_or_create_distinct_id(env_path=env_file)

    lines = [l for l in env_file.read_text().splitlines() if l.startswith("POSTHOG_DISTINCT_ID=")]
    assert len(lines) == 1


# ---------------------------------------------------------------------------
# .env file handling — key absent from file
# ---------------------------------------------------------------------------

def test_appends_key_when_absent_from_existing_file(tmp_path):
    """Appends POSTHOG_DISTINCT_ID when the key is not present in the file."""
    env_file = tmp_path / ".env"
    env_file.write_text("POSTHOG_API_KEY=abc\n")

    result = get_or_create_distinct_id(env_path=env_file)

    content = env_file.read_text()
    assert f"POSTHOG_DISTINCT_ID={result}" in content
    assert "POSTHOG_API_KEY=abc" in content


# ---------------------------------------------------------------------------
# .env file handling — file does not exist
# ---------------------------------------------------------------------------

def test_creates_env_file_when_missing(tmp_path):
    """Creates the .env file containing the new ID when no file exists."""
    env_file = tmp_path / ".env"
    assert not env_file.exists()

    result = get_or_create_distinct_id(env_path=env_file)

    assert env_file.exists()
    assert f"POSTHOG_DISTINCT_ID={result}" in env_file.read_text()


# ---------------------------------------------------------------------------
# Write errors
# ---------------------------------------------------------------------------

def test_returns_id_even_when_file_write_fails(tmp_path):
    """Returns a valid in-memory ID even when the .env file cannot be written."""
    env_file = tmp_path / ".env"
    env_file.write_text("POSTHOG_DISTINCT_ID=\n")
    env_file.chmod(0o444)  # read-only

    try:
        result = get_or_create_distinct_id(env_path=env_file)
        assert result  # non-empty UUID returned in-memory
        assert os.environ.get("POSTHOG_DISTINCT_ID") == result
    finally:
        env_file.chmod(0o644)  # restore so tmp_path cleanup can delete it


# ---------------------------------------------------------------------------
# UUID validity
# ---------------------------------------------------------------------------

def test_generated_id_is_valid_uuid4(tmp_path):
    """The generated ID is a well-formed UUID4."""
    env_file = tmp_path / ".env"
    result = get_or_create_distinct_id(env_path=env_file)
    parsed = uuid.UUID(result)  # raises ValueError if malformed
    assert parsed.version == 4


def test_each_new_generation_produces_unique_id(tmp_path):
    """Two separate calls on fresh files produce different IDs."""
    file_a = tmp_path / "a.env"
    file_b = tmp_path / "b.env"

    id_a = get_or_create_distinct_id(env_path=file_a)
    os.environ.pop("POSTHOG_DISTINCT_ID", None)
    id_b = get_or_create_distinct_id(env_path=file_b)

    assert id_a != id_b


# ---------------------------------------------------------------------------
# os.environ side effect
# ---------------------------------------------------------------------------

def test_sets_env_var_after_generation(tmp_path):
    """After generating an ID, os.environ["POSTHOG_DISTINCT_ID"] is set."""
    assert "POSTHOG_DISTINCT_ID" not in os.environ
    result = get_or_create_distinct_id(env_path=tmp_path / ".env")
    assert os.environ.get("POSTHOG_DISTINCT_ID") == result


def test_idempotent_across_calls_via_env(tmp_path):
    """A second call returns the same ID (from env), without rewriting the file."""
    env_file = tmp_path / ".env"

    first = get_or_create_distinct_id(env_path=env_file)
    mtime_after_first = env_file.stat().st_mtime

    second = get_or_create_distinct_id(env_path=env_file)
    mtime_after_second = env_file.stat().st_mtime

    assert first == second
    assert mtime_after_first == mtime_after_second  # file not rewritten


# ---------------------------------------------------------------------------
# inject_pipeline_session_id — scout-to-submit funnel linkage
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=False)
def clear_pipeline_session_id():
    """Remove PIPELINE_SESSION_ID from env before and after each test."""
    os.environ.pop("PIPELINE_SESSION_ID", None)
    yield
    os.environ.pop("PIPELINE_SESSION_ID", None)


def test_inject_adds_session_id_when_env_var_set(clear_pipeline_session_id):
    """Injects session_id from PIPELINE_SESSION_ID when the property is absent."""
    os.environ["PIPELINE_SESSION_ID"] = "run-abc-123"
    props = {"event": "scout_complete", "jobs_found": 5}

    inject_pipeline_session_id(props)

    assert props["session_id"] == "run-abc-123"


def test_inject_does_not_overwrite_explicit_session_id(clear_pipeline_session_id):
    """Does not overwrite a session_id already present in properties."""
    os.environ["PIPELINE_SESSION_ID"] = "from-env"
    props = {"session_id": "from-caller"}

    inject_pipeline_session_id(props)

    assert props["session_id"] == "from-caller"


def test_inject_no_op_when_env_var_absent(clear_pipeline_session_id):
    """Leaves properties unchanged when PIPELINE_SESSION_ID is not set."""
    props = {"jobs_found": 3}

    inject_pipeline_session_id(props)

    assert "session_id" not in props


def test_inject_no_op_when_env_var_empty(clear_pipeline_session_id):
    """Treats an empty PIPELINE_SESSION_ID as absent."""
    os.environ["PIPELINE_SESSION_ID"] = "   "
    props = {}

    inject_pipeline_session_id(props)

    assert "session_id" not in props


def test_inject_returns_same_dict(clear_pipeline_session_id):
    """Returns the same dict object (mutates in place)."""
    os.environ["PIPELINE_SESSION_ID"] = "run-xyz"
    props = {}

    result = inject_pipeline_session_id(props)

    assert result is props


# ---------------------------------------------------------------------------
# compute_cost_per_app — cost per application formula
# ---------------------------------------------------------------------------

def test_cost_per_app_basic():
    """Divides total cost by submitted count and rounds to 4 decimal places."""
    assert compute_cost_per_app(1.0, 4) == 0.25


def test_cost_per_app_rounds_to_4dp():
    """Result is rounded to 4 decimal places."""
    result = compute_cost_per_app(1.0, 3)
    assert result == round(1.0 / 3, 4)


def test_cost_per_app_returns_none_when_zero_submitted():
    """Returns None when no applications were submitted (avoids division by zero)."""
    assert compute_cost_per_app(5.0, 0) is None


def test_cost_per_app_returns_none_when_negative_submitted():
    """Returns None for negative submitted counts."""
    assert compute_cost_per_app(5.0, -1) is None


def test_cost_per_app_zero_cost():
    """Returns 0.0 when there was no API cost."""
    assert compute_cost_per_app(0.0, 10) == 0.0


def test_cost_per_app_single_submission():
    """Cost equals total_cost when exactly one app was submitted."""
    assert compute_cost_per_app(2.5678, 1) == 2.5678
