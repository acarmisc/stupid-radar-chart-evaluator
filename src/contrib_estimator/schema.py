"""Pydantic models for LLM I/O and final output."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, conint

Score = conint(ge=0, le=100)
ScopeMode = Literal["repo", "commit", "mr"]


class AxisScores(BaseModel):
    """LLM-classified scores for one chunk. Independent 0-100 axes."""

    author: Score = Field(description="Single human contributor authorship signal")
    ai: Score = Field(description="LLM-generated code signal")
    team: Score = Field(description="Multi-contributor / code-review signal")
    research: Score = Field(description="External copy/tutorial/snippet signal")
    unspecified: Score = Field(description="Generated / vendored / unknown provenance")


class Coverage(BaseModel):
    files_seen: int
    files_scored: int
    sampled: bool


class Scope(BaseModel):
    mode: ScopeMode
    ref: Optional[str] = None
    base: Optional[str] = None
    head: Optional[str] = None


class Metadata(BaseModel):
    project: str
    languages: list[str]
    checked_at: datetime


class ProvenanceSummary(BaseModel):
    """Deterministic repo-wide priors. Surfaced for transparency."""
    total_commits: int
    ai_footer_rate: float
    agentic_author_rate: float
    conventional_rate: float
    msg_uniformity: float
    emoji_ai_rate: float
    avg_body_length: float
    burstiness: float
    peak_commits_per_day: int
    distinct_human_authors: int
    top_human_share: float
    n_significant_humans: int
    todo_per_kloc: float
    doc_to_code_ratio: float
    has_ai_workflow: bool
    scaffold_score: Score
    committed_artifacts: int
    ai_prior: Score
    author_prior: Score
    team_prior: Score
    research_prior: Score


class VerboseResult(BaseModel):
    scores: AxisScores
    metadata: Metadata
    coverage: Coverage
    scope: Scope
    provenance: Optional[ProvenanceSummary] = None
