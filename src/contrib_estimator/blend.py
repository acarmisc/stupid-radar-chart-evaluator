"""Blend LLM scores with deterministic repo priors.

Research backing (fusion beats single-signal across the AICD literature):
- Commit-message conventions are MORE discriminative than code content (Fingerprinting AI Coding Agents, 2025).
- LLM-as-judge suffers verbosity bias and metadata blindness.
- Fusing LLM output with structural+git priors consistently lifts F1 by 5-10 pp.

We use a fixed convex blend per axis. Priors only exist for axes where
deterministic signals are strong (ai, author, team). research and unspecified
stay LLM-only.
"""
from __future__ import annotations

from .collect.provenance import Provenance
from .schema import AxisScores

# Per-axis blend weight on the prior (rest goes to the LLM score)
PRIOR_WEIGHT = {
    "ai": 0.5,         # very strong deterministic signals available
    "author": 0.3,     # weaker — single-author signal less reliable
    "team": 0.4,       # moderate — distinct-author count is strong
    "research": 0.0,   # no deterministic prior — leave to LLM
    "unspecified": 0.0,
}


def apply(scores: AxisScores, prov: Provenance) -> AxisScores:
    """Return prior-blended scores. Pure function, idempotent if prior=score."""
    blended = {
        "ai":          _blend(scores.ai, prov.ai_prior, PRIOR_WEIGHT["ai"]),
        "author":      _blend(scores.author, prov.author_prior, PRIOR_WEIGHT["author"]),
        "team":        _blend(scores.team, prov.team_prior, PRIOR_WEIGHT["team"]),
        "research":    scores.research,
        "unspecified": scores.unspecified,
    }
    return AxisScores(**blended)


def _blend(llm: int, prior: int, w_prior: float) -> int:
    return max(0, min(100, round((1 - w_prior) * llm + w_prior * prior)))
