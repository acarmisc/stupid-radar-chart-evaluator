"""Reproducibility test against a reference repo's deterministic provenance.

Only the deterministic provenance signals are checked. The test is skipped if the
recorded source repo path is missing, so it runs cleanly in CI without requiring
the fixture repo to be present locally.
"""
import json
from pathlib import Path

import pytest

from contrib_estimator.collect import provenance

GOLDEN = Path(__file__).parent / "golden" / "reference_provenance.json"
DETERMINISTIC_KEYS = (
    "total_commits", "ai_footer_rate", "agentic_author_rate",
    "conventional_rate", "msg_uniformity",
    "emoji_ai_rate", "avg_body_length",
    "burstiness",
    "peak_commits_per_day", "distinct_human_authors",
    "top_human_share", "n_significant_humans",
    "todo_per_kloc", "doc_to_code_ratio", "has_ai_workflow",
    "scaffold_score", "committed_artifacts",
    "ai_prior", "author_prior", "team_prior", "research_prior",
)


def _load_golden() -> dict:
    return json.loads(GOLDEN.read_text())


def test_golden_fixture_well_formed():
    g = _load_golden()
    for k in DETERMINISTIC_KEYS:
        assert k in g, f"missing {k} in golden fixture"


def test_reference_provenance_reproduces():
    """Skipped unless the source repo is checked out at the recorded path."""
    g = _load_golden()
    src = Path(g["_source_repo"])
    if not (src / ".git").exists():
        pytest.skip(f"source repo not present at {src}")

    actual = provenance.collect(src)
    for k in DETERMINISTIC_KEYS:
        expected = g[k]
        got = getattr(actual, k)
        if isinstance(expected, float):
            assert abs(got - expected) < 1e-6, f"{k}: golden={expected} got={got}"
        else:
            assert got == expected, f"{k}: golden={expected} got={got}"
