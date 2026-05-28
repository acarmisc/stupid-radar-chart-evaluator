"""Weighted mean per axis. Weights = lines of evidence per chunk."""
from __future__ import annotations

from .schema import AxisScores

AXES = ("author", "ai", "team", "research", "unspecified")


def reduce_scores(scored: list[tuple[AxisScores, int]]) -> AxisScores:
    """scored = list of (axis_scores, weight). Weight = LOC or lines_changed."""
    if not scored:
        return AxisScores(author=0, ai=0, team=0, research=0, unspecified=0)
    totals = {a: 0.0 for a in AXES}
    wsum = 0
    for s, w in scored:
        w = max(w, 1)
        wsum += w
        for a in AXES:
            totals[a] += getattr(s, a) * w
    return AxisScores(**{a: round(totals[a] / wsum) for a in AXES})
