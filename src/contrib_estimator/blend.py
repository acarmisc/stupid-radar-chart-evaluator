"""Blend LLM scores with deterministic repo priors.

Research backing (fusion beats single-signal across the AICD literature):
- Commit-message conventions are MORE discriminative than code content
  (Fingerprinting AI Coding Agents, 2025).
- LLM-as-judge suffers verbosity bias and metadata blindness — well-structured
  human-looking code gets mislabeled as human even when metadata screams AI.
- Fusing LLM output with structural + git priors consistently lifts F1 by 5-10 pp.

We use an ADAPTIVE convex blend per axis. Base weights apply when no strong
meta-signal is present. When a high-confidence repo signature is detected
(IDE-Copilot, sole-author, large team), the prior weight is boosted on the
affected axes to override LLM verbosity bias.

v1 weights tuned against a 3-repo calibration set spanning the score-space corners
(vibe-coded cyborg / AI+tutorial / human team).
"""
from __future__ import annotations

from .collect.provenance import Provenance
from .schema import AxisScores

# Base blend weight on the prior (rest goes to LLM).
BASE_PRIOR_WEIGHT = {
    "ai": 0.5,
    "author": 0.5,
    "team": 0.3,
    "research": 0.3,
    "unspecified": 0.0,
}

# When strong meta-signals fire, prior weight goes UP on the affected axes
# (LLM judgement is known to be unreliable in these cases).
BOOSTED_PRIOR_WEIGHT = {
    "ai": 0.75,        # IDE-Copilot: code looks human-clean but is AI
    "author": 0.75,    # mirror of ai (anti-correlated)
    "team": 0.5,       # high n_significant: trust the head count more
    "research": 0.5,   # many AI-flow docs: trust the scaffold signal more
}


def _trigger_strong_ai_prior(prov: Provenance) -> bool:
    """Repo is heavily AI-derived but the LLM is likely to be fooled:
    workflow files present AND deterministic ai_prior is high AND explicit
    metadata under-reports (IDE-Copilot rather than committed Co-Authored-By).
    """
    explicit = max(prov.ai_footer_rate, prov.agentic_author_rate)
    return prov.has_ai_workflow and prov.ai_prior >= 65 and explicit < 0.30


def _trigger_strong_team_prior(prov: Provenance) -> bool:
    """Many significant contributors → trust the head count over LLM judgement."""
    return prov.n_significant_humans >= 4


def _trigger_strong_research_prior(prov: Provenance) -> bool:
    """Many AI-flow docs / scaffolds present → LLM rarely catches this."""
    return prov.scaffold_score >= 60


def apply(scores: AxisScores, prov: Provenance) -> AxisScores:
    """Return prior-blended scores. Pure function, idempotent if prior=score."""
    strong_ai = _trigger_strong_ai_prior(prov)
    strong_team = _trigger_strong_team_prior(prov)
    strong_research = _trigger_strong_research_prior(prov)

    w_ai = BOOSTED_PRIOR_WEIGHT["ai"] if strong_ai else BASE_PRIOR_WEIGHT["ai"]
    w_author = BOOSTED_PRIOR_WEIGHT["author"] if strong_ai else BASE_PRIOR_WEIGHT["author"]
    w_team = BOOSTED_PRIOR_WEIGHT["team"] if strong_team else BASE_PRIOR_WEIGHT["team"]
    w_research = BOOSTED_PRIOR_WEIGHT["research"] if strong_research else BASE_PRIOR_WEIGHT["research"]

    blended = {
        "ai":          _blend(scores.ai, prov.ai_prior, w_ai),
        "author":      _blend(scores.author, prov.author_prior, w_author),
        "team":        _blend(scores.team, prov.team_prior, w_team),
        "research":    _blend(scores.research, prov.research_prior, w_research),
        "unspecified": scores.unspecified,
    }
    return AxisScores(**blended)


def _blend(llm: int, prior: int, w_prior: float) -> int:
    return max(0, min(100, round((1 - w_prior) * llm + w_prior * prior)))
