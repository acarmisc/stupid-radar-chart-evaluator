"""CLI entry point.

Pre-flight validation, progress feedback, dry-run + list-models utilities.
Each command path fails fast with a friendly hint when env/config is wrong.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import click
from dotenv import load_dotenv

from . import __version__
from .config import Config

# Load .env from CWD before any Config.from_env() reads.
load_dotenv()

EXIT_USAGE = 2
EXIT_CONFIG = 3
EXIT_REMOTE = 4


def _replace_config(cfg, **kw):
    from dataclasses import replace
    return replace(cfg, **kw)


# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

def _check_git_repo(repo: Path) -> None:
    """Fail early if the path is not a usable git repo."""
    if not (repo / ".git").exists():
        raise click.ClickException(
            f"{repo} does not look like a git repo (no .git/ directory). "
            f"Pass --repo to the project root, or run from inside a git checkout."
        )
    try:
        out = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=repo, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        raise click.ClickException(
            f"{repo} has no commits to analyze (`git rev-list HEAD` failed)."
        )
    if out == "0":
        raise click.ClickException(f"{repo} has zero commits.")


def _check_ref_exists(repo: Path, ref: str) -> None:
    try:
        subprocess.run(
            ["git", "rev-parse", "--verify", ref],
            cwd=repo, capture_output=True, check=True,
        )
    except subprocess.CalledProcessError:
        raise click.ClickException(
            f"Ref '{ref}' is not resolvable in {repo}. "
            f"Try `git fetch` or check the SHA / branch name."
        )


def _check_llm_config(cfg: Config) -> None:
    """Fail with a helpful hint when credentials are missing."""
    missing = []
    if not cfg.litellm_base_url or cfg.litellm_base_url == "http://localhost:4000":
        missing.append("LITELLM_BASE_URL")
    if not cfg.litellm_key:
        missing.append("LITELLM_KEY")
    if missing:
        hint = (
            "Set them in `.env` next to the project, or export them in your shell.\n"
            "  cp .env.example .env  # then fill in real values"
        )
        raise click.ClickException(
            f"Missing required env vars: {', '.join(missing)}.\n{hint}"
        )


# ---------------------------------------------------------------------------
# Main CLI group
# ---------------------------------------------------------------------------

@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="contrib-estimator")
def main() -> None:
    """Estimate codebase contribution sources as a 5-axis radar chart.

    Examples:

      \b
      contrib-estimator estimate --repo .
      contrib-estimator estimate --repo . --scope commit --ref HEAD~1
      contrib-estimator estimate --scope mr --base main --head feature-x --verbose
      contrib-estimator estimate --dry-run        # priors only, no LLM calls
      contrib-estimator list-models               # probe LiteLLM gateway

    Credentials are read from a `.env` file in the working directory:

      \b
      LITELLM_BASE_URL=https://...
      LITELLM_KEY=sk-...
      MODEL_CLASSIFY=openai/...
    """


# ---------------------------------------------------------------------------
# estimate — the main command
# ---------------------------------------------------------------------------

@main.command()
@click.option("--repo", type=click.Path(exists=True, file_okay=False, path_type=Path),
              default=Path.cwd(), show_default="cwd", help="Path to git repo.")
@click.option("--scope", type=click.Choice(["repo", "commit", "mr"]), default="repo",
              show_default=True)
@click.option("--ref", default=None, help="Commit SHA / ref (scope=commit).")
@click.option("--base", default=None, help="Base ref (scope=mr).")
@click.option("--head", default=None, help="Head ref (scope=mr).")
@click.option("--verbose", is_flag=True,
              help="Include metadata, coverage, scope, provenance in output.")
@click.option("--out", type=click.Path(path_type=Path), default=None,
              help="Write JSON to file instead of stdout.")
@click.option("--max-chunks", type=int, default=None, help="Override MAX_CHUNKS.")
@click.option("--seed", type=int, default=None, help="Override sampling seed.")
@click.option("--dry-run", is_flag=True,
              help="Compute deterministic priors only; skip LLM calls. "
                   "Useful for a quick sanity check on a new repo.")
@click.option("--log-level", default="WARNING",
              type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
              show_default=True)
def estimate(repo, scope, ref, base, head, verbose, out, max_chunks, seed,
             dry_run, log_level):
    """Run an estimation against a repo, commit, or MR range."""
    logging.basicConfig(level=log_level, format="%(levelname)s %(name)s: %(message)s")
    _check_git_repo(repo)

    cfg = Config.from_env()
    if max_chunks is not None:
        cfg = _replace_config(cfg, max_chunks=max_chunks)
    if seed is not None:
        cfg = _replace_config(cfg, seed=seed)

    if scope == "commit":
        if not ref:
            raise click.UsageError("--ref is required for --scope commit.")
        _check_ref_exists(repo, ref)
    elif scope == "mr":
        if not (base and head):
            raise click.UsageError("--base and --head are required for --scope mr.")
        _check_ref_exists(repo, base)
        _check_ref_exists(repo, head)

    if dry_run:
        payload = _dry_run_payload(repo)
    else:
        _check_llm_config(cfg)
        payload = _live_run_payload(cfg, repo, scope, ref, base, head, verbose)

    text = json.dumps(payload, indent=2 if (verbose or dry_run) else None)
    if out:
        out.write_text(text)
        click.echo(f"wrote {out}", err=True)
    else:
        click.echo(text)


def _live_run_payload(cfg, repo, scope, ref, base, head, verbose):
    # Imported lazily so dry-run + list-models don't pay the litellm import cost.
    from .pipeline import run_diff, run_repo

    if scope == "repo":
        final, verbose_out = run_repo(cfg, repo)
    else:
        final, verbose_out = run_diff(cfg, repo, scope, ref, base, head)
    return verbose_out.model_dump(mode="json") if verbose else final.model_dump()


def _dry_run_payload(repo: Path) -> dict:
    """Compute deterministic provenance only. No LLM, no LiteLLM key required."""
    from .collect import provenance

    prov = provenance.collect(repo)
    return {
        "dry_run": True,
        "priors": {
            "ai": prov.ai_prior, "author": prov.author_prior,
            "team": prov.team_prior, "research": prov.research_prior,
        },
        "summary": prov.summary_for_prompt(),
    }


# ---------------------------------------------------------------------------
# list-models — probe the gateway
# ---------------------------------------------------------------------------

@main.command("list-models")
def list_models_cmd() -> None:
    """List models reachable through the configured LiteLLM gateway.

    Requires LITELLM_BASE_URL and LITELLM_KEY. The gateway team policy
    determines what's actually visible — the master key sees more.
    """
    import urllib.error
    import urllib.request

    cfg = Config.from_env()
    _check_llm_config(cfg)

    url = cfg.litellm_base_url.rstrip("/") + "/v1/models"
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {cfg.litellm_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:200]
        raise click.ClickException(
            f"Gateway returned HTTP {e.code} from {url}\n{body}"
        )
    except urllib.error.URLError as e:
        raise click.ClickException(f"Cannot reach gateway {url}: {e.reason}")

    models = [m.get("id", "?") for m in data.get("data", [])]
    if not models:
        raise click.ClickException("Gateway responded but listed zero models.")
    for m in sorted(models):
        click.echo(m)


# ---------------------------------------------------------------------------
# version — also exposed top-level via --version
# ---------------------------------------------------------------------------

@main.command()
def version() -> None:
    """Print the installed package version."""
    click.echo(__version__)


if __name__ == "__main__":
    main()
