"""Tests for prompt versioning — SYSTEM_PROMPT loaded from file, version tracked."""
from __future__ import annotations

from pathlib import Path

import content_finder as cf

_ROOT = Path(__file__).resolve().parent.parent


def test_prompt_file_exists():
    """prompts/synthesis_system.md must exist on disk."""
    prompt_file = _ROOT / "prompts" / "synthesis_system.md"
    assert prompt_file.exists(), f"prompt file not found at {prompt_file}"


def test_prompt_version_is_non_empty_string():
    """PROMPT_VERSION must be a non-empty string constant."""
    assert hasattr(cf, "PROMPT_VERSION"), "content_finder must export PROMPT_VERSION"
    assert isinstance(cf.PROMPT_VERSION, str)
    assert cf.PROMPT_VERSION.strip(), "PROMPT_VERSION must not be empty"


def test_system_prompt_matches_file():
    """SYSTEM_PROMPT must equal the content of prompts/synthesis_system.md."""
    prompt_file = _ROOT / "prompts" / "synthesis_system.md"
    expected = prompt_file.read_text()
    assert cf.SYSTEM_PROMPT == expected, (
        "SYSTEM_PROMPT does not match prompts/synthesis_system.md — "
        "the file and the module constant are out of sync"
    )


def test_filter_log_records_prompt_version(monkeypatch):
    """FilterLog.prompt_version must equal PROMPT_VERSION."""
    monkeypatch.setattr(cf, "RSS_SOURCES", [])
    monkeypatch.setattr(cf, "HN_QUERIES", [])
    monkeypatch.setattr(cf, "dedupe", lambda items: items)

    _, log = cf.gather(days=1, hn_min_points=50)
    assert log.prompt_version == cf.PROMPT_VERSION
