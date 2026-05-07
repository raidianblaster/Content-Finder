"""Tests for sources.yml loading, validation, and module-level wiring.

Coverage:
  - File presence
  - Correct return types from load_sources()
  - Schema validation (https URLs, no duplicates, trust range, required keys)
  - Error paths (missing file, bad key, bad URL, bad trust, bad weight key)
  - Custom-path loading via tmp_path
  - Module constants match what load_sources() returns
  - score_item() trust comes from YAML (regression guard)
"""
from __future__ import annotations

import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

import content_finder as cf
from content_finder import SourceConfig, load_sources


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_RSS = [{"name": "Test Feed", "url": "https://example.com/feed.xml", "trust": 1}]
_DEFAULT_HN = ["AI agents"]
_DEFAULT_KW = {3: ["agentic"], 1: ["regulation"]}


def _make_minimal_yml(
    rss: list[dict] | None = None,
    hn: list[str] | None = None,
    kw: dict | None = None,
) -> str:
    """Return a valid minimal sources.yml string.

    Pass an empty list explicitly to test empty-list validation; None uses the default.
    """
    data = {
        "rss_sources": _DEFAULT_RSS if rss is None else rss,
        "hn_queries": _DEFAULT_HN if hn is None else hn,
        "keyword_weights": _DEFAULT_KW if kw is None else kw,
    }
    return yaml.dump(data)


# ---------------------------------------------------------------------------
# File presence
# ---------------------------------------------------------------------------

def test_sources_yml_exists():
    root = Path(cf.__file__).resolve().parent
    assert (root / "sources.yml").exists(), "sources.yml must exist next to content_finder.py"


# ---------------------------------------------------------------------------
# Return-type shape
# ---------------------------------------------------------------------------

def test_load_sources_returns_source_config():
    cfg = load_sources()
    assert isinstance(cfg, SourceConfig)


def test_rss_sources_is_list_of_tuples():
    cfg = load_sources()
    assert isinstance(cfg.rss_sources, list)
    for entry in cfg.rss_sources:
        assert isinstance(entry, tuple) and len(entry) == 2, (
            f"rss_sources entries must be (name, url) tuples, got {entry!r}"
        )
        name, url = entry
        assert isinstance(name, str) and name
        assert isinstance(url, str) and url


def test_hn_queries_is_list_of_strings():
    cfg = load_sources()
    assert isinstance(cfg.hn_queries, list)
    for q in cfg.hn_queries:
        assert isinstance(q, str) and q, f"empty/non-string HN query: {q!r}"


def test_keyword_weights_shape():
    cfg = load_sources()
    assert isinstance(cfg.keyword_weights, dict)
    for k, v in cfg.keyword_weights.items():
        assert isinstance(k, int) and k > 0, f"weight key must be positive int, got {k!r}"
        assert isinstance(v, list), f"weight values must be lists, got {v!r}"
        for term in v:
            assert isinstance(term, str) and term, f"empty/non-string keyword: {term!r}"


def test_trusted_weights_maps_names_to_ints():
    cfg = load_sources()
    assert isinstance(cfg.trusted_weights, dict)
    for name, trust in cfg.trusted_weights.items():
        assert isinstance(name, str) and name
        assert isinstance(trust, int)


# ---------------------------------------------------------------------------
# Content invariants (real sources.yml)
# ---------------------------------------------------------------------------

def test_rss_sources_nonempty():
    assert len(load_sources().rss_sources) > 0


def test_hn_queries_nonempty():
    assert len(load_sources().hn_queries) > 0


def test_keyword_weights_nonempty():
    assert len(load_sources().keyword_weights) > 0


def test_all_rss_urls_are_https():
    cfg = load_sources()
    for name, url in cfg.rss_sources:
        assert url.startswith("https://"), f"{name!r} URL must be https, got {url!r}"


def test_no_duplicate_source_names():
    cfg = load_sources()
    names = [name for name, _ in cfg.rss_sources]
    assert len(names) == len(set(names)), "duplicate source names found"


def test_trust_values_in_valid_range():
    cfg = load_sources()
    for name, trust in cfg.trusted_weights.items():
        assert 0 <= trust <= 5, f"{name!r} trust={trust} outside 0-5"


def test_trusted_weights_only_contains_known_sources():
    cfg = load_sources()
    source_names = {name for name, _ in cfg.rss_sources}
    for name in cfg.trusted_weights:
        assert name in source_names, (
            f"trusted_weights has {name!r} which is not in rss_sources"
        )


# ---------------------------------------------------------------------------
# Module constants match loaded config
# ---------------------------------------------------------------------------

def test_module_rss_sources_matches_loaded():
    cfg = load_sources()
    assert cf.RSS_SOURCES == cfg.rss_sources


def test_module_hn_queries_matches_loaded():
    cfg = load_sources()
    assert cf.HN_QUERIES == cfg.hn_queries


def test_module_keyword_weights_matches_loaded():
    cfg = load_sources()
    assert cf.KEYWORD_WEIGHTS == cfg.keyword_weights


# ---------------------------------------------------------------------------
# Custom-path loading (tmp_path)
# ---------------------------------------------------------------------------

def test_load_sources_custom_path(tmp_path):
    yml = _make_minimal_yml()
    p = tmp_path / "sources.yml"
    p.write_text(yml)
    cfg = load_sources(p)
    assert cfg.rss_sources == [("Test Feed", "https://example.com/feed.xml")]
    assert cfg.hn_queries == ["AI agents"]
    assert cfg.keyword_weights == {3: ["agentic"], 1: ["regulation"]}


def test_load_sources_trust_extracted_to_trusted_weights(tmp_path):
    yml = _make_minimal_yml(
        rss=[
            {"name": "A", "url": "https://a.example.com/feed.xml", "trust": 3},
            {"name": "B", "url": "https://b.example.com/feed.xml"},  # no trust = 0
        ]
    )
    p = tmp_path / "sources.yml"
    p.write_text(yml)
    cfg = load_sources(p)
    assert cfg.trusted_weights.get("A") == 3
    assert cfg.trusted_weights.get("B", 0) == 0


def test_load_sources_zero_trust_not_in_trusted_weights(tmp_path):
    """Sources with trust=0 (or omitted) should not appear in trusted_weights."""
    yml = _make_minimal_yml(
        rss=[{"name": "NoTrust", "url": "https://notrust.example.com/feed.xml"}]
    )
    p = tmp_path / "sources.yml"
    p.write_text(yml)
    cfg = load_sources(p)
    assert "NoTrust" not in cfg.trusted_weights


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_load_sources_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_sources(Path("/nonexistent/sources.yml"))


def test_load_sources_missing_rss_key_raises(tmp_path):
    p = tmp_path / "sources.yml"
    p.write_text(yaml.dump({"hn_queries": ["x"], "keyword_weights": {1: ["y"]}}))
    with pytest.raises(ValueError, match="rss_sources"):
        load_sources(p)


def test_load_sources_missing_hn_key_raises(tmp_path):
    p = tmp_path / "sources.yml"
    p.write_text(yaml.dump({
        "rss_sources": [{"name": "X", "url": "https://x.com/feed.xml"}],
        "keyword_weights": {1: ["y"]},
    }))
    with pytest.raises(ValueError, match="hn_queries"):
        load_sources(p)


def test_load_sources_missing_keyword_weights_key_raises(tmp_path):
    p = tmp_path / "sources.yml"
    p.write_text(yaml.dump({
        "rss_sources": [{"name": "X", "url": "https://x.com/feed.xml"}],
        "hn_queries": ["x"],
    }))
    with pytest.raises(ValueError, match="keyword_weights"):
        load_sources(p)


def test_load_sources_nonhttps_url_raises(tmp_path):
    yml = _make_minimal_yml(
        rss=[{"name": "Bad", "url": "http://bad.example.com/feed.xml"}]
    )
    p = tmp_path / "sources.yml"
    p.write_text(yml)
    with pytest.raises(ValueError, match="https"):
        load_sources(p)


def test_load_sources_duplicate_names_raises(tmp_path):
    yml = _make_minimal_yml(
        rss=[
            {"name": "Dupe", "url": "https://a.example.com/feed.xml"},
            {"name": "Dupe", "url": "https://b.example.com/feed.xml"},
        ]
    )
    p = tmp_path / "sources.yml"
    p.write_text(yml)
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        load_sources(p)


def test_load_sources_trust_out_of_range_raises(tmp_path):
    yml = _make_minimal_yml(
        rss=[{"name": "X", "url": "https://x.example.com/feed.xml", "trust": 9}]
    )
    p = tmp_path / "sources.yml"
    p.write_text(yml)
    with pytest.raises(ValueError, match="trust"):
        load_sources(p)


def test_load_sources_negative_trust_raises(tmp_path):
    yml = _make_minimal_yml(
        rss=[{"name": "X", "url": "https://x.example.com/feed.xml", "trust": -1}]
    )
    p = tmp_path / "sources.yml"
    p.write_text(yml)
    with pytest.raises(ValueError, match="trust"):
        load_sources(p)


def test_load_sources_nonpositive_weight_key_raises(tmp_path):
    yml = _make_minimal_yml(kw={0: ["term"]})
    p = tmp_path / "sources.yml"
    p.write_text(yml)
    with pytest.raises(ValueError, match="[Ww]eight"):
        load_sources(p)


def test_load_sources_empty_rss_list_raises(tmp_path):
    yml = _make_minimal_yml(rss=[])
    p = tmp_path / "sources.yml"
    p.write_text(yml)
    with pytest.raises(ValueError, match="rss_sources"):
        load_sources(p)


def test_load_sources_rss_entry_missing_name_raises(tmp_path):
    p = tmp_path / "sources.yml"
    p.write_text(yaml.dump({
        "rss_sources": [{"url": "https://x.com/feed.xml"}],
        "hn_queries": ["x"],
        "keyword_weights": {1: ["y"]},
    }))
    with pytest.raises(ValueError, match="name"):
        load_sources(p)


def test_load_sources_rss_entry_missing_url_raises(tmp_path):
    p = tmp_path / "sources.yml"
    p.write_text(yaml.dump({
        "rss_sources": [{"name": "X"}],
        "hn_queries": ["x"],
        "keyword_weights": {1: ["y"]},
    }))
    with pytest.raises(ValueError, match="url"):
        load_sources(p)


def test_load_sources_empty_hn_list_raises(tmp_path):
    yml = _make_minimal_yml(hn=[])
    p = tmp_path / "sources.yml"
    p.write_text(yml)
    with pytest.raises(ValueError, match="hn_queries"):
        load_sources(p)


# ---------------------------------------------------------------------------
# score_item() uses trust from YAML (regression guard)
# ---------------------------------------------------------------------------

def test_score_item_uses_trust_from_yaml():
    """score_item() must use the YAML-sourced trust weights, not a hardcoded dict."""
    cfg = load_sources()
    # Find the highest-trust source from YAML.
    if not cfg.trusted_weights:
        pytest.skip("no trusted sources in sources.yml")
    top_source = max(cfg.trusted_weights, key=cfg.trusted_weights.__getitem__)
    top_trust = cfg.trusted_weights[top_source]

    ts = datetime.now(timezone.utc)
    item_trusted = cf.Item(title="probe", url="https://a.com/x", source=top_source, published=ts)
    item_unknown = cf.Item(title="probe", url="https://b.com/x", source="UnknownSource999", published=ts)

    score_trusted = cf.score_item(item_trusted)
    score_unknown = cf.score_item(item_unknown)
    assert score_trusted > score_unknown, (
        f"trusted source {top_source!r} (trust={top_trust}) should score higher than unknown"
    )
