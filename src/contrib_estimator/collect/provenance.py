"""Repo-wide AI/human provenance signals. Computed once per run, injected as priors.

Signal selection is research-backed:
- Co-Authored-By footers + AI author names: "Fingerprinting AI Coding Agents on GitHub"
  (arxiv 2601.17406, 2025) — commit metadata is more discriminative than code content.
- Commit-message uniformity + conventional-commits compliance: same study.
- Burstiness (inter-commit time variance): humans pause to think; AI runs in tight loops.
- TODO/FIXME density: humans leave debt, AI doesn't ("Debt Behind the AI Boom",
  arxiv 2603.28592).
- Documentation-to-code ratio: AI workflows over-document.
- Multi-signal fusion beats any single signal (TriFusion-LLM, arxiv 2603.15004).
"""
from __future__ import annotations

import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# Author-name patterns that signal AI co-authorship.
# Right-side \b catches "RiccardoAgent" (Agent at end); left-side allows CamelCase.
AI_AUTHOR_RE = re.compile(
    r"(?i)(agent(ic)?[a-z-]*\b|copilot|cursor|claude|chatgpt|codex|aider|"
    r"\bbot\b|ai-?ops?\b|\bllm\b|devin|windsurf)"
)

# Commit-footer co-author markers
AI_FOOTER_RE = re.compile(
    r"(?im)^Co-Authored-By:\s*(Claude|Cursor|Copilot|GPT|Codex|Aider|Devin)"
)

# Conventional commits prefix
CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|chore|refactor|docs|test|style|perf|build|ci)(\([^)]+\))?: "
)

# TODO markers (any language)
TODO_RE = re.compile(r"(?i)\b(TODO|FIXME|XXX|HACK)\b")

# Files that indicate explicit AI workflow
AI_WORKFLOW_FILES = (
    "CLAUDE.md", "AGENTS.md", ".cursorrules", ".cursor/rules",
    ".github/copilot-instructions.md", ".aider.conf.yml",
    ".claude/", ".windsurfrules",
)


@dataclass
class Provenance:
    total_commits: int
    ai_footer_rate: float          # 0-1: commits with Co-Authored-By AI
    agentic_author_rate: float     # 0-1: commits from AI-named authors
    conventional_rate: float       # 0-1: conventional-commits compliance
    msg_uniformity: float          # 0-1: fraction of commits sharing top-3 subject prefixes
    burstiness: float              # 0-1: fraction of inter-commit gaps under 60s
    peak_commits_per_day: int      # max commits any single calendar day
    distinct_human_authors: int    # authors NOT matching AI pattern
    top_human_share: float         # 0-1: largest single human's commit share
    n_significant_humans: int      # humans contributing >=5% of human commits
    todo_per_kloc: float           # TODO+FIXME+XXX per 1000 LOC
    doc_to_code_ratio: float       # md LOC / code LOC
    has_ai_workflow: bool          # CLAUDE.md / .cursorrules / etc present
    scaffold_score: int            # 0-100: tutorial-scaffold marker sum
    ai_prior: int                  # 0-100 derived prior for ai axis
    author_prior: int              # 0-100 derived prior for single-author axis
    team_prior: int                # 0-100 derived prior for team axis
    research_prior: int            # 0-100 derived prior for research axis

    def summary_for_prompt(self) -> str:
        """Compact one-line summary to inject into LLM prompt as repo-level prior."""
        return (
            f"Repo priors: ai_footer={self.ai_footer_rate:.0%}, "
            f"agentic_authors={self.agentic_author_rate:.0%}, "
            f"top_human_share={self.top_human_share:.0%}, "
            f"significant_humans={self.n_significant_humans}, "
            f"conventional_commits={self.conventional_rate:.0%}, "
            f"msg_uniformity={self.msg_uniformity:.0%}, "
            f"burstiness={self.burstiness:.2f}, "
            f"peak_commits/day={self.peak_commits_per_day}, "
            f"todo_per_kloc={self.todo_per_kloc:.2f}, "
            f"doc_ratio={self.doc_to_code_ratio:.2f}, "
            f"ai_workflow_files={'yes' if self.has_ai_workflow else 'no'}, "
            f"scaffold_score={self.scaffold_score}"
        )


def _run(args: list[str], cwd: Path) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
        ).stdout
    except subprocess.CalledProcessError:
        return ""


def _commit_signals(repo: Path) -> dict:
    """Walk full log once, collect aggregate signals.

    Format uses %ct (committer unix timestamp) for burstiness, %ad short date
    for daily aggregation, and null-byte field separators with ---END--- record
    sentinel to survive multiline commit bodies.
    """
    out = _run(
        ["log", "--all",
         "--format=%H%x00%an%x00%ad%x00%ct%x00%B%x00---END---",
         "--date=short"],
        repo,
    )
    if not out:
        return {
            "total": 0, "ai_footer": 0, "agentic": 0, "conv": 0,
            "by_day": {}, "human_counts": Counter(),
            "timestamps": [], "subjects": [],
        }

    total = ai_footer = agentic = conv = 0
    by_day: dict[str, int] = {}
    human_counts: Counter = Counter()
    timestamps: list[int] = []
    subjects: list[str] = []

    for record in out.split("---END---"):
        record = record.strip()
        if not record:
            continue
        parts = record.split("\0", 4)
        if len(parts) < 5:
            continue
        _sha, author, date, ts, body = parts
        total += 1
        by_day[date] = by_day.get(date, 0) + 1
        try:
            timestamps.append(int(ts))
        except ValueError:
            pass

        if AI_AUTHOR_RE.search(author):
            agentic += 1
        else:
            human_counts[author.strip()] += 1

        if AI_FOOTER_RE.search(body):
            ai_footer += 1

        subject = body.split("\n", 1)[0]
        subjects.append(subject)
        if CONVENTIONAL_RE.match(subject):
            conv += 1

    return {
        "total": total, "ai_footer": ai_footer, "agentic": agentic,
        "conv": conv, "by_day": by_day, "human_counts": human_counts,
        "timestamps": timestamps, "subjects": subjects,
    }


def _burstiness(timestamps: list[int]) -> float:
    """Fraction of inter-commit gaps under 60 seconds.

    Tight back-to-back commits are an AI-agent signature (auto-commit-per-edit).
    Humans rarely commit within 60s of the previous commit. This metric is
    robust to long idle periods (unlike CV-based burstiness).
    """
    if len(timestamps) < 3:
        return 0.0
    ts = sorted(timestamps)
    gaps = [ts[i] - ts[i - 1] for i in range(1, len(ts))]
    if not gaps:
        return 0.0
    under_60s = sum(1 for g in gaps if 0 <= g <= 60)
    return under_60s / len(gaps)


# Strip conventional-commit type+scope to extract the verb/topic that follows.
_CONV_STRIP_RE = re.compile(r"^(feat|fix|chore|refactor|docs|test|style|perf|build|ci)(\([^)]+\))?:\s*")


def _normalize_subject(subject: str) -> str:
    """Drop conventional prefix, lowercase, take first 3 words. Captures the
    actual semantic verb of the commit, ignoring the prefix discipline."""
    s = _CONV_STRIP_RE.sub("", subject.strip()).lower()
    return " ".join(s.split()[:3])


def _msg_uniformity(subjects: list[str]) -> float:
    """Top-5 normalized subjects' share of all commits.

    High share = templated/repetitive bodies (AI agent loop signature).
    Conventional-commit prefixes are stripped before counting so the metric
    captures actual semantic repetition, not just `feat:` discipline.
    """
    if not subjects:
        return 0.0
    norms = [_normalize_subject(s) for s in subjects if s.strip()]
    if not norms:
        return 0.0
    counts = Counter(norms)
    top5 = sum(c for _, c in counts.most_common(5))
    return top5 / len(norms)


def _code_doc_loc(repo: Path) -> tuple[int, int, int]:
    """Return (code_loc, doc_loc, todo_count) by scanning tracked files."""
    out = _run(["ls-files"], repo)
    code_exts = (".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".go", ".rs")
    code_loc = doc_loc = todo_count = 0
    for rel in out.splitlines():
        p = repo / rel
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lines = text.count("\n") + 1
        if rel.endswith(".md"):
            doc_loc += lines
        elif rel.endswith(code_exts):
            code_loc += lines
            todo_count += len(TODO_RE.findall(text))
    return code_loc, doc_loc, todo_count


def _has_ai_workflow(repo: Path) -> bool:
    return any((repo / name).exists() for name in AI_WORKFLOW_FILES)


# Scaffolding files that indicate tutorial/research-derived starter code.
# Each entry is (path-fragment-to-check, points). Points sum into research_prior.
SCAFFOLD_MARKERS = (
    ("alembic", 20),                # SQLAlchemy migration scaffold
    ("alembic.ini", 0),             # implied by alembic dir; avoid double-count
    ("manage.py", 15),              # Django scaffold
    (".env.example", 10),
    (".env.sample", 10),
    ("docker-compose.yml", 10),
    ("docker-compose.yaml", 10),
    ("Dockerfile", 5),
    ("Procfile", 5),                # Heroku tutorial
    ("requirements-dev.txt", 5),
    ("Pipfile", 5),
    ("pnpm-workspace.yaml", 5),
)


def _scaffold_score(repo: Path) -> int:
    """Sum of points for present scaffolding files. Capped to 100."""
    score = 0
    seen: set[str] = set()
    for marker, points in SCAFFOLD_MARKERS:
        # Avoid double-counting alembic (dir) AND alembic.ini
        key = marker.split(".")[0]
        if key in seen:
            continue
        if (repo / marker).exists():
            score += points
            seen.add(key)

    # Large README often = tutorial-derived. Boost for README > 5 KB.
    readme = repo / "README.md"
    if readme.exists():
        try:
            kb = readme.stat().st_size / 1024
            score += min(20, int(kb))
        except OSError:
            pass
    return min(100, score)


def _author_team_priors(human_counts: Counter) -> tuple[int, int, list[float]]:
    """Compute author + team priors from human commit-volume distribution.

    Returns (author_prior, team_prior, shares).

    author_prior = round(100 * top_share). One dominant human → ~100.
    team_prior   = scales with number of significant contributors (>=5% each):
                   1 → 0, 2 → 25, 3 → 50, 4 → 75, 5+ → 100.
    """
    if not human_counts:
        return 0, 0, []
    total = sum(human_counts.values()) or 1
    shares = sorted((c / total for c in human_counts.values()), reverse=True)
    top_share = shares[0]
    n_significant = sum(1 for s in shares if s >= 0.05)

    author_prior = round(100 * top_share)
    team_prior = round(min(100, max(0, 25 * (n_significant - 1))))
    return author_prior, team_prior, shares


def _compute_priors(
    s: dict, code_loc: int, doc_loc: int, todo_count: int,
    ai_workflow: bool, burstiness: float, msg_uniformity: float,
    scaffold_score: int,
) -> tuple[int, int, int, int]:
    """Derive 0-100 priors (ai, author, team, research) from raw signals.

    v1 changes vs v0:
    - author/team priors use commit-volume distribution (top_share + n_significant)
      instead of distinct-name count. Fixes mercurio over-team / under-author drift.
    - AI prior boosted by IDE-Copilot signature (workflow files present + low
      explicit attribution): catches finna-app pattern where Copilot/Cursor used
      in IDE without `Co-Authored-By` footers.
    - ai_workflow weight raised 10 → 20 points (workflow file presence is a much
      stronger signal in practice than the original heuristic admitted).
    - research_prior added (was missing): scaffolding-file detection.
    """
    total = max(s["total"], 1)
    ai_footer_rate = s["ai_footer"] / total
    agentic_rate = s["agentic"] / total
    conv_rate = s["conv"] / total
    peak = max(s["by_day"].values()) if s["by_day"] else 0

    todo_per_kloc = (todo_count / max(code_loc, 1)) * 1000
    doc_ratio = doc_loc / max(code_loc, 1)

    explicit_ai = max(ai_footer_rate, agentic_rate)
    # IDE-Copilot signature: AI workflow files present but git metadata is silent.
    # Means the human runs an AI coding agent in-editor without committing as such.
    ide_copilot_signal = ai_workflow and explicit_ai < 0.25

    ai_score = (
        35 * explicit_ai                         # direct AI authorship
        + 10 * min(conv_rate, 1.0)               # automated commit style
        + 10 * min(peak / 50, 1.0)               # commit velocity
        + 20 * (1.0 if ai_workflow else 0.0)     # workflow files (was 10)
        + 5  * max(0, 1 - todo_per_kloc / 2)     # low TODO debt
        + 5  * min(doc_ratio, 1.0)               # over-documentation
        + 10 * burstiness                        # tight commit loops
        + 5  * min(max(msg_uniformity - 0.2, 0) / 0.6, 1.0)
        + (25 if ide_copilot_signal else 0)      # IDE-only AI flow boost
    )

    author_prior, team_prior, _ = _author_team_priors(s["human_counts"])

    research_prior = scaffold_score

    return (
        max(0, min(100, round(ai_score))),
        author_prior,
        team_prior,
        max(0, min(100, research_prior)),
    )


def collect(repo: Path) -> Provenance:
    """Single entry point. Cheap — runs in 1-2 seconds on most repos."""
    s = _commit_signals(repo)
    code_loc, doc_loc, todo_count = _code_doc_loc(repo)
    ai_workflow = _has_ai_workflow(repo)
    burstiness = _burstiness(s["timestamps"])
    msg_uniformity = _msg_uniformity(s["subjects"])
    scaffold_score = _scaffold_score(repo)

    _, _, shares = _author_team_priors(s["human_counts"])
    top_share = shares[0] if shares else 0.0
    n_significant = sum(1 for sh in shares if sh >= 0.05)

    ai_prior, author_prior, team_prior, research_prior = _compute_priors(
        s, code_loc, doc_loc, todo_count, ai_workflow, burstiness, msg_uniformity, scaffold_score
    )

    total = max(s["total"], 1)
    peak = max(s["by_day"].values()) if s["by_day"] else 0
    return Provenance(
        total_commits=s["total"],
        ai_footer_rate=s["ai_footer"] / total,
        agentic_author_rate=s["agentic"] / total,
        conventional_rate=s["conv"] / total,
        msg_uniformity=msg_uniformity,
        burstiness=burstiness,
        peak_commits_per_day=peak,
        distinct_human_authors=len(s["human_counts"]),
        top_human_share=top_share,
        n_significant_humans=n_significant,
        todo_per_kloc=(todo_count / max(code_loc, 1)) * 1000,
        doc_to_code_ratio=doc_loc / max(code_loc, 1),
        has_ai_workflow=ai_workflow,
        scaffold_score=scaffold_score,
        ai_prior=ai_prior,
        author_prior=author_prior,
        team_prior=team_prior,
        research_prior=research_prior,
    )
