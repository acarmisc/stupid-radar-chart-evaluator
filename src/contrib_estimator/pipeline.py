"""Glue: collect → classify → blend → aggregate. Decoupled from CLI for testability."""
from __future__ import annotations

import logging
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import blend
from .aggregate import reduce_scores
from .classify.llm import classify_chunk
from .collect import git, provenance, tree
from .config import Config
from .sampler import stratify
from .schema import (
    AxisScores, Coverage, Metadata, ProvenanceSummary, Scope, VerboseResult,
)

log = logging.getLogger(__name__)


def _blame_authors(repo: Path, rel: str) -> list[str]:
    """Distinct authors who touched the file. Empty on error."""
    try:
        out = subprocess.run(
            ["git", "log", "--format=%an", "--", rel],
            cwd=repo, capture_output=True, text=True, check=True,
        ).stdout
    except subprocess.CalledProcessError:
        return []
    seen: list[str] = []
    for name in out.splitlines():
        if name and name not in seen:
            seen.append(name)
    return seen


def _provenance_summary(p: provenance.Provenance) -> ProvenanceSummary:
    return ProvenanceSummary(**asdict(p))


def run_repo(cfg: Config, repo: Path) -> tuple[AxisScores, VerboseResult]:
    prov = provenance.collect(repo)
    log.info("provenance: %s", prov.summary_for_prompt())
    priors_str = prov.summary_for_prompt()

    files = git.list_files(repo, cfg.max_file_kb)
    sampled, was_sampled = stratify(files, cfg.max_chunks, cfg.seed)

    scored: list[tuple[AxisScores, int]] = []
    used_budget = 0
    for f in sampled:
        try:
            code = f.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        est_tokens = len(code) // 4
        if used_budget + est_tokens > cfg.max_tokens_budget:
            log.info("token budget exhausted at %d files", len(scored))
            break
        feats = tree.features_dict(tree.extract(f.path))
        authors = _blame_authors(repo, f.rel)
        result = classify_chunk(cfg, f.rel, authors, feats, code, repo_priors=priors_str)
        if result:
            scored.append((result, max(f.churn_90d, 1)))
            used_budget += est_tokens

    aggregated = reduce_scores(scored)
    final = blend.apply(aggregated, prov)

    verbose = VerboseResult(
        scores=final,
        metadata=Metadata(
            project=git.project_name(repo),
            languages=git.detect_languages(sampled),
            checked_at=datetime.now(timezone.utc),
        ),
        coverage=Coverage(files_seen=len(files), files_scored=len(scored), sampled=was_sampled),
        scope=Scope(mode="repo"),
        provenance=_provenance_summary(prov),
    )
    return final, verbose


def run_diff(cfg: Config, repo: Path, mode: str, ref: Optional[str], base: Optional[str], head: Optional[str]) -> tuple[AxisScores, VerboseResult]:
    """Scope: commit or mr. Chunk = hunk.

    Commit-scope evaluation now sends the commit subject + body + footer +
    branch hint + stat to the LLM alongside the diff. Without this context
    the LLM cannot see the most discriminative signal at commit scope: the
    `Co-Authored-By:` footer and AI-style body. Repo-level priors alone
    cannot differentiate commit-level provenance.
    """
    prov = provenance.collect(repo)
    priors_str = prov.summary_for_prompt()

    if mode == "commit":
        assert ref, "--ref required for commit scope"
        hunks = git.hunks_for_commit(repo, ref)
        cmeta = git.commit_metadata(repo, ref)
    else:
        assert base and head, "--base and --head required for mr scope"
        hunks = git.hunks_for_range(repo, base, head)
        cmeta = git.range_metadata(repo, base, head)

    commit_context = cmeta.to_prompt_block() if cmeta else ""

    scored: list[tuple[AxisScores, int]] = []
    used_budget = 0
    files_touched: set[str] = set()
    for h in hunks[: cfg.max_chunks]:
        # Prepend commit context to the hunk content so the LLM sees the
        # commit message body + Co-Authored-By footer on every chunk.
        chunk_text = (commit_context + "\n\n--- Patch ---\n" + h.content) if commit_context else h.content
        est_tokens = len(chunk_text) // 4
        if used_budget + est_tokens > cfg.max_tokens_budget:
            break
        files_touched.add(h.file_rel)
        authors = _blame_authors(repo, h.file_rel)
        result = classify_chunk(cfg, h.file_rel, authors, {}, chunk_text, repo_priors=priors_str)
        if result:
            scored.append((result, h.lines_changed))
            used_budget += est_tokens

    # Merge commits + empty commits show no diff via `git show`. Still send
    # ONE LLM call with just the commit metadata so the merge/empty commit
    # gets scored on its body + footer alone.
    if not scored and commit_context:
        result = classify_chunk(
            cfg, "(commit metadata only)", [cmeta.author] if cmeta else [],
            {}, commit_context, repo_priors=priors_str,
        )
        if result:
            scored.append((result, max(cmeta.insertions + cmeta.deletions if cmeta else 1, 1)))

    aggregated = reduce_scores(scored)
    final = blend.apply(aggregated, prov)

    fake_entries = [
        git.FileEntry(path=repo / f, rel=f, size_bytes=0, churn_90d=0)
        for f in files_touched
    ]
    verbose = VerboseResult(
        scores=final,
        metadata=Metadata(
            project=git.project_name(repo),
            languages=git.detect_languages(fake_entries),
            checked_at=datetime.now(timezone.utc),
        ),
        coverage=Coverage(
            files_seen=len(files_touched),
            files_scored=len(scored),
            sampled=len(hunks) > cfg.max_chunks,
        ),
        scope=Scope(mode=mode, ref=ref, base=base, head=head),
        provenance=_provenance_summary(prov),
    )
    return final, verbose
