# Benchmarks

Per-repo evaluation of `contrib-estimator` against ground-truth labels.

## Layout

```
benchmarks/
├── README.md              # this file — methodology + how to add a repo
├── CALIBRATION.md         # drift analysis vs ground truth + tuning history
├── <repo-slug>/
│   ├── GROUND_TRUTH.md    # human-labeled expected scores + rationale
│   ├── BENCHMARK.md       # results vs ground truth + per-model deltas
│   ├── benchmark.json     # reference --verbose snapshot (default model, larger sample)
│   ├── provenance.json    # deterministic priors subset
│   └── models/
│       └── <model>.json   # one --verbose snapshot per model tested
```

## How to add a repo

1. Get ground-truth labels from the repo's owner: scores for `author`, `ai`, `team`, `research`, `unspecified` (0-100 each, independent). Record rationale and date.
2. Create `benchmarks/<slug>/GROUND_TRUTH.md` with the labels.
3. Run the pipeline with the default model, save reference output:
   ```bash
   contrib-estimator --repo <path> --max-chunks 25 --verbose \
     --out benchmarks/<slug>/benchmark.json
   ```
4. Extract the deterministic provenance subset → `provenance.json`.
5. Optionally run per-model comparison via `scripts/bench-models.sh <slug> <repo-path>` (TBD).
6. Update `CALIBRATION.md` with the per-axis delta and any new tuning decisions.

## Why ground truth matters

The agent fuses deterministic git-metadata signals (commit footers, agentic-author names, TODO density, burstiness, etc.) with LLM-judged per-file scores. Both layers have biases:

- **Priors** baked from git can over-weight explicit AI markers when a human heavily uses Copilot without `Co-Authored-By`.
- **LLM judges** suffer verbosity bias (well-structured human code looks AI).
- **Blend weights** were initially set heuristically (`w_ai=0.5`, `w_author=0.3`, `w_team=0.4`) and need calibration against varied repos.

Three reference repos give us a calibration triangle:

| Repo | author | ai | team | research | uns. | Profile |
|------|------:|---:|----:|---------:|----:|---------|
| `govtool` (vibe-coded) | low | high | mid | low | low | Mixed human+AI cyborg |
| `finna-app` | 20 | 90 | low | 80 | low | AI + tutorial-derived |
| `mercurio-ms-benefits` | 80 | 10 | 60 | low | low | Real team, human-written |

Together these cover the corners of the score space: a vibe-coded mid-team, a tutorial-shaped AI app, and a real human team.

## Acceptable tolerance

- Per-axis target: `|score - ground_truth| ≤ 15`
- Direction errors (e.g. predicting AI=20 when truth=90) are critical failures
- `unspecified` ≤ 10 when there's any meaningful provenance signal

## Re-running

Set credentials in `.env`, then:
```bash
contrib-estimator --repo <path> --max-chunks 25 --verbose
```

For per-model comparison, override `MODEL_CLASSIFY` per run.
