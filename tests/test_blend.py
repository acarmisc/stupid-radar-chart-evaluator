"""Unit tests for the adaptive blend.

Verifies that strong-meta-signal triggers raise the prior weight on the
affected axes (LLM-judge bias mitigation)."""
from contrib_estimator.blend import (
    BASE_PRIOR_WEIGHT, BOOSTED_PRIOR_WEIGHT, apply,
    _trigger_strong_ai_prior, _trigger_strong_team_prior, _trigger_strong_research_prior,
)
from contrib_estimator.schema import AxisScores, ProvenanceSummary


def _prov(**kw) -> ProvenanceSummary:
    """Make a ProvenanceSummary with sane defaults; kw overrides any field."""
    defaults = dict(
        total_commits=100, ai_footer_rate=0.0, agentic_author_rate=0.0,
        conventional_rate=0.0, msg_uniformity=0.0,
        emoji_ai_rate=0.0, avg_body_length=0.0,
        burstiness=0.0,
        peak_commits_per_day=5, distinct_human_authors=1,
        top_human_share=1.0, n_significant_humans=1,
        todo_per_kloc=0.0, doc_to_code_ratio=0.0, has_ai_workflow=False,
        scaffold_score=0, committed_artifacts=0,
        ai_prior=0, author_prior=0, team_prior=0, research_prior=0,
    )
    defaults.update(kw)
    return ProvenanceSummary(**defaults)


def test_strong_ai_trigger_fires_for_ide_copilot():
    p = _prov(has_ai_workflow=True, ai_prior=75, ai_footer_rate=0.1, agentic_author_rate=0.1)
    assert _trigger_strong_ai_prior(p)


def test_strong_ai_trigger_misses_when_no_workflow():
    p = _prov(has_ai_workflow=False, ai_prior=75)
    assert not _trigger_strong_ai_prior(p)


def test_strong_ai_trigger_misses_when_explicit_already_high():
    p = _prov(has_ai_workflow=True, ai_prior=75, ai_footer_rate=0.5)
    assert not _trigger_strong_ai_prior(p)  # gov-tool-like: metadata already tells the truth


def test_strong_team_trigger_above_threshold():
    assert _trigger_strong_team_prior(_prov(n_significant_humans=4))
    assert _trigger_strong_team_prior(_prov(n_significant_humans=10))
    assert not _trigger_strong_team_prior(_prov(n_significant_humans=3))


def test_strong_research_trigger_above_threshold():
    assert _trigger_strong_research_prior(_prov(scaffold_score=60))
    assert _trigger_strong_research_prior(_prov(scaffold_score=100))
    assert not _trigger_strong_research_prior(_prov(scaffold_score=50))


def test_apply_blend_base_weights_when_no_trigger():
    # Plain repo: ai_prior=10, llm says ai=50 → blend = 0.5*50 + 0.5*10 = 30
    p = _prov(ai_prior=10, author_prior=90)
    llm = AxisScores(author=70, ai=50, team=20, research=20, unspecified=0)
    result = apply(llm, p)
    assert result.ai == 30
    assert result.author == round(0.5 * 70 + 0.5 * 90)


def test_apply_blend_boosts_ai_when_trigger_fires():
    # IDE-Copilot signature → ai weight should be 0.75 not 0.5
    p = _prov(has_ai_workflow=True, ai_prior=80, author_prior=20,
              ai_footer_rate=0.1, agentic_author_rate=0.1)
    llm = AxisScores(author=80, ai=20, team=0, research=0, unspecified=0)
    result = apply(llm, p)
    # 0.25*20 + 0.75*80 = 65
    assert result.ai == 65
    assert result.author == round(0.25 * 80 + 0.75 * 20)


def test_blend_weights_are_well_formed():
    for axis, w in BASE_PRIOR_WEIGHT.items():
        assert 0 <= w <= 1, f"BASE[{axis}]={w}"
    for axis, w in BOOSTED_PRIOR_WEIGHT.items():
        assert 0 <= w <= 1, f"BOOST[{axis}]={w}"
        assert w >= BASE_PRIOR_WEIGHT[axis], f"BOOST[{axis}] should >= BASE[{axis}]"
