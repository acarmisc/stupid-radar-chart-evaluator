"""Git interactions. All ops shell out to `git` — no extra deps."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

# Supported languages → file extensions
LANG_EXT = {
    "python": {".py"},
    "typescript": {".ts", ".tsx"},
    "javascript": {".js", ".jsx", ".mjs", ".cjs"},
    "java": {".java"},
}
ALL_EXTS = {ext for exts in LANG_EXT.values() for ext in exts}

# Always skip these path fragments
SKIP_FRAGMENTS = (
    "node_modules/", ".venv/", "venv/", "dist/", "build/",
    "vendor/", "target/", ".git/", "__pycache__/",
)
SKIP_SUFFIXES = (".min.js", ".min.css", ".generated.ts", ".generated.js")
LOCK_FILES = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "Pipfile.lock"}


@dataclass
class FileEntry:
    """One tracked file with churn metric for sampling weight."""
    path: Path
    rel: str
    size_bytes: int
    churn_90d: int  # lines changed in last 90 days


@dataclass
class Hunk:
    """One diff hunk from commit or MR scope."""
    file_rel: str
    content: str  # the +/- patch text
    lines_changed: int


def _run(args: list[str], cwd: Path) -> str:
    """Run git command, return stdout. Raises on non-zero."""
    res = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )
    return res.stdout


def project_name(repo: Path) -> str:
    """Use remote origin basename if present, else dir name."""
    try:
        url = _run(["config", "--get", "remote.origin.url"], repo).strip()
        if url:
            return url.rstrip("/").split("/")[-1].removesuffix(".git")
    except subprocess.CalledProcessError:
        pass
    return repo.resolve().name


def primary_author(repo: Path) -> Optional[str]:
    """Most prolific author by commit count."""
    try:
        out = _run(["shortlog", "-sne", "HEAD"], repo)
    except subprocess.CalledProcessError:
        return None
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if not lines:
        return None
    # "  123  Name <email>"
    return lines[0].split(None, 1)[1] if " " in lines[0] else None


def _is_target(rel: str) -> bool:
    if any(frag in rel for frag in SKIP_FRAGMENTS):
        return False
    if rel.endswith(SKIP_SUFFIXES):
        return False
    name = rel.rsplit("/", 1)[-1]
    if name in LOCK_FILES:
        return False
    return any(rel.endswith(ext) for ext in ALL_EXTS)


def detect_languages(files: Iterable[FileEntry]) -> list[str]:
    """Languages present in scored files, ordered by file count desc."""
    counts: dict[str, int] = {}
    for f in files:
        for lang, exts in LANG_EXT.items():
            if any(f.rel.endswith(e) for e in exts):
                counts[lang] = counts.get(lang, 0) + 1
                break
    return [lang for lang, _ in sorted(counts.items(), key=lambda kv: -kv[1])]


def list_files(repo: Path, max_file_kb: int) -> list[FileEntry]:
    """All tracked target-language files within size cap."""
    out = _run(["ls-files"], repo)
    entries: list[FileEntry] = []
    for rel in out.splitlines():
        if not _is_target(rel):
            continue
        p = repo / rel
        if not p.is_file():
            continue
        size = p.stat().st_size
        if size > max_file_kb * 1024:
            continue
        entries.append(FileEntry(path=p, rel=rel, size_bytes=size, churn_90d=0))
    _annotate_churn(repo, entries)
    return entries


def _annotate_churn(repo: Path, entries: list[FileEntry]) -> None:
    """Set churn_90d in place via single `git log --numstat` pass."""
    by_rel = {e.rel: e for e in entries}
    try:
        out = _run(
            ["log", "--since=90.days", "--numstat", "--pretty=format:"], repo
        )
    except subprocess.CalledProcessError:
        return
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, removed, rel = parts
        if rel not in by_rel:
            continue
        try:
            by_rel[rel].churn_90d += int(added) + int(removed)
        except ValueError:
            pass  # binary diffs show "-"


def hunks_for_commit(repo: Path, ref: str) -> list[Hunk]:
    return _parse_hunks(_run(["show", "--no-color", "--unified=3", ref], repo))


def hunks_for_range(repo: Path, base: str, head: str) -> list[Hunk]:
    return _parse_hunks(_run(["diff", "--no-color", "--unified=3", f"{base}...{head}"], repo))


def _parse_hunks(diff: str) -> list[Hunk]:
    """Split unified diff into per-file hunks, filtered by target ext."""
    hunks: list[Hunk] = []
    current_file: Optional[str] = None
    buf: list[str] = []
    changed = 0

    def flush():
        if current_file and buf and _is_target(current_file):
            hunks.append(Hunk(file_rel=current_file, content="\n".join(buf), lines_changed=changed))

    for line in diff.splitlines():
        if line.startswith("diff --git"):
            flush()
            buf, changed = [], 0
            # "diff --git a/path b/path"
            try:
                current_file = line.split(" b/", 1)[1]
            except IndexError:
                current_file = None
        elif line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            buf.append(line)
            changed += 1
        else:
            buf.append(line)
    flush()
    return hunks
