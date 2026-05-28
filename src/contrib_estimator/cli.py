"""CLI entry point."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

from .config import Config
from .pipeline import run_diff, run_repo

# Load .env from CWD or repo root before Config.from_env reads
load_dotenv()


@click.command()
@click.option("--repo", type=click.Path(exists=True, file_okay=False, path_type=Path), default=Path.cwd(), help="Path to git repo.")
@click.option("--scope", type=click.Choice(["repo", "commit", "mr"]), default="repo")
@click.option("--ref", default=None, help="Commit SHA (scope=commit).")
@click.option("--base", default=None, help="Base ref (scope=mr).")
@click.option("--head", default=None, help="Head ref (scope=mr).")
@click.option("--verbose", is_flag=True, help="Include metadata, coverage, scope in output.")
@click.option("--out", type=click.Path(path_type=Path), default=None, help="Write JSON to file instead of stdout.")
@click.option("--max-chunks", type=int, default=None, help="Override MAX_CHUNKS.")
@click.option("--seed", type=int, default=None, help="Override sampling seed.")
@click.option("--log-level", default="WARNING", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]))
def main(repo, scope, ref, base, head, verbose, out, max_chunks, seed, log_level):
    """Estimate contribution sources for a codebase."""
    logging.basicConfig(level=log_level, format="%(levelname)s %(name)s: %(message)s")
    cfg = Config.from_env()
    if max_chunks is not None:
        cfg = _replace(cfg, max_chunks=max_chunks)
    if seed is not None:
        cfg = _replace(cfg, seed=seed)

    if scope == "repo":
        final, verbose_out = run_repo(cfg, repo)
    else:
        final, verbose_out = run_diff(cfg, repo, scope, ref, base, head)

    payload = verbose_out.model_dump(mode="json") if verbose else final.model_dump()
    text = json.dumps(payload, indent=2 if verbose else None)
    if out:
        out.write_text(text)
    else:
        click.echo(text)


def _replace(cfg, **kw):
    """dataclass replace without importing dataclasses at top (frozen)."""
    from dataclasses import replace
    return replace(cfg, **kw)


if __name__ == "__main__":
    main()
