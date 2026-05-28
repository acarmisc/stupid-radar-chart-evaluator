"""Unit tests for deterministic provenance signals.

These run against synthetic inputs — no git repo needed."""
from contrib_estimator.collect.provenance import (
    AI_AUTHOR_RE, AI_FOOTER_RE, CONVENTIONAL_RE,
    _burstiness, _msg_uniformity, _normalize_subject,
)


def test_ai_author_regex_hits():
    for name in ["Riccardo Agentic", "RiccardoAgent", "riccardoagentic-ops",
                 "Cursor Agent", "Claude Bot", "Devin", "windsurf-bot"]:
        assert AI_AUTHOR_RE.search(name), f"missed: {name}"


def test_ai_author_regex_misses_humans():
    for name in ["Riccardo", "Abstract", "Daniele Salvato", "acarmisc", "Andrea"]:
        assert not AI_AUTHOR_RE.search(name), f"false hit: {name}"


def test_ai_footer_detects_claude():
    body = "feat: add thing\n\nCo-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
    assert AI_FOOTER_RE.search(body)


def test_conventional_commits():
    assert CONVENTIONAL_RE.match("feat(api): add endpoint")
    assert CONVENTIONAL_RE.match("fix: handle null")
    assert not CONVENTIONAL_RE.match("Add new feature")


def test_normalize_subject_strips_prefix():
    assert _normalize_subject("feat(allocation-engine): ordina i progetti") == "ordina i progetti"
    assert _normalize_subject("fix: handle null") == "handle null"
    assert _normalize_subject("Update README") == "update readme"


def test_burstiness_zero_for_human_pace():
    # 10 commits spaced 1 hour apart → no <60s gaps
    ts = [3600 * i for i in range(10)]
    assert _burstiness(ts) == 0.0


def test_burstiness_high_for_ai_agent():
    # 10 commits all within 30s of each other → 100%
    ts = [10 * i for i in range(10)]
    assert _burstiness(ts) == 1.0


def test_burstiness_mixed():
    # Half tight, half spread
    ts = [0, 10, 20, 30, 4000, 8000]  # 3 of 5 gaps under 60s
    assert _burstiness(ts) == 3 / 5


def test_msg_uniformity_low_for_diverse():
    subjects = [f"feat: add feature {i}" for i in range(20)]
    # All normalized to unique 3-word subjects → top-5 = 5/20
    assert _msg_uniformity(subjects) == 5 / 20


def test_msg_uniformity_high_for_templated():
    subjects = ["chore: update dependencies"] * 20
    # All identical → top-5 (just 1 unique) = 20/20
    assert _msg_uniformity(subjects) == 1.0
