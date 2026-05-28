# Calibration

Drift analysis vs ground-truth labels and the resulting tuning history.

## Reference repos

| Repo | author | ai | team | research | uns. | Profile |
|------|------:|---:|----:|---------:|----:|---------|
| govtool | 25-40 | 75-90 | 30-50 | 5-20 | 0-10 | Mixed human + AI cyborg |
| finna-app | **20** | **90** | low | **80** | low | AI + tutorial-derived |
| mercurio-ms-benefits | **80** | **10** | **60** | low | low | Real team, human-written |

## Calibration v0 — initial fine-tuned pipeline

**Stack**: kimi-k2.5 default; provenance (`ai_footer`, `agentic_authors`, `conv_rate`, `burstiness`, `msg_uniformity`, `peak/day`, `todo/kloc`, `doc/code`, `ai_workflow`); convex blend (`w_ai=0.5`, `w_author=0.3`, `w_team=0.4`).

### Results (granite4.1:8b via Ollama — gateway was down during run)

| Repo | axis | predicted | expected | delta | severity |
|------|------|----------:|---------:|------:|----------|
| govtool | ai | 70 | 75-90 | -5 to -20 | ⚠ acceptable |
| govtool | author | 29 | 25-40 | 0 | ✓ |
| govtool | team | 39 | 30-50 | 0 | ✓ |
| **finna-app** | author | 73 | 20 | **+53** | ❌ direction wrong |
| **finna-app** | ai | 33 | 90 | **-57** | ❌ direction wrong |
| **finna-app** | research | 14 | 80 | **-66** | ❌ direction wrong |
| **finna-app** | team | 24 | low | +14 | ✓ |
| mercurio | author | 71 | 80 | -9 | ✓ |
| mercurio | ai | 10 | 10 | 0 | ✓ |
| mercurio | team | 62 | 60 | +2 | ✓ |

**Pass**: govtool, mercurio.
**Fail**: finna-app — three critical direction errors on `author`, `ai`, `research`.

### Why mercurio passed despite bad priors

`author_prior=20`, `team_prior=96` are both wrong (distinct-name count formula). But the granite LLM scored per-file `author` very high and `team` moderate, and the **0.3/0.4 blend weights** were small enough that LLM judgement dominated. Lucky escape on a broken formula.

### Why finna-app failed

1. **Provenance can't see in-IDE AI use** — finna-app's git metadata shows only 17% `Co-Authored-By: Claude` and 18% agentic-named authors. Ground truth says AI=90. The owner clearly uses Copilot/Cursor *in IDE* without commit attribution. The deterministic priors are blind to this.
2. **No `research` prior** — research axis is 100% LLM-dependent. Granite missed the tutorial scaffolding (alembic, AGENTS.md, ACTION-PLAN.md).
3. **`ai_workflow_files=yes` underweighted** — current formula gives this 10/100. finna-app has `AGENTS.md` + `ACTION-PLAN.md` + `COMPLETION_REPORT.md` (super-strong AI-flow signature). Should weight higher.

## Root-cause summary

| # | Issue | Affects | Fix |
|---|-------|---------|-----|
| 1 | `author_prior` formula counts distinct names instead of volume concentration | mercurio (correctly handled by LLM, lucky), would fail other team repos | Use top-author-share (HHI / Gini) |
| 2 | `team_prior` formula scales linearly on distinct count → ceiling 96 | mercurio gets over-counted | Use n_significant_contributors with concentration weighting |
| 3 | No `research` prior; LLM-only | finna-app fails | Add scaffolding-file detection (alembic, manage.py, .env.example, Dockerfile defaults, README size) |
| 4 | In-IDE AI (Copilot/Cursor without commit attribution) is invisible | finna-app fails ai axis | Boost `ai_prior` when `ai_workflow=yes` AND footer+agentic share is low (indicates IDE-only flow) |
| 5 | `ai_workflow_files=yes` worth only 10 points | finna-app under-scored on ai | Re-weight: 20 points + amplify when other signals weak |

## Calibration v1 — planned changes

### Author / team prior rewrite

```python
# Per-author commit counts (HUMAN AUTHORS ONLY — agentic excluded)
shares = sorted(human_commit_counts, reverse=True)
total = sum(shares) or 1
shares = [s / total for s in shares]
top_share = shares[0] if shares else 0.0
n_significant = sum(1 for s in shares if s >= 0.05)  # contributed >= 5%

author_prior = round(100 * top_share)
team_prior = round(min(100, 25 * (n_significant - 1)))  # 1→0, 3→50, 5→100
```

Predictions on the 3 calibration repos (estimated from `git shortlog`):
- govtool: Riccardo ~55% of human commits, n_sig=2-3 → author~55 team~25-50 ✓
- finna-app: 1 author dominant → author~85 team~0 ✓ (matches ground truth direction)
- mercurio: top dev ~40-60%, n_sig ~3-5 → author~50 team~50-100 (closer to 80/60 ground truth)

### Research prior

```python
scaffold_score = 0
if (repo / "alembic").exists() or (repo / "alembic.ini").exists(): scaffold_score += 20
if (repo / "manage.py").exists(): scaffold_score += 15
if (repo / ".env.example").exists() or (repo / ".env.sample").exists(): scaffold_score += 10
if (repo / "docker-compose.yml").exists(): scaffold_score += 10
if (repo / "Dockerfile").exists(): scaffold_score += 5
readme_loc = (repo / "README.md").stat().st_size / 1024 if (repo / "README.md").exists() else 0
if readme_loc > 5: scaffold_score += min(20, readme_loc)  # large READMEs ≈ tutorial-derived
research_prior = min(100, scaffold_score)
```

### AI prior re-weight for IDE-Copilot signature

```python
# Detect "IDE-Copilot signature": AI workflow files present but low footer+agentic
explicit_ai = max(ai_footer_rate, agentic_rate)
ide_copilot_signal = ai_workflow and explicit_ai < 0.25
if ide_copilot_signal:
    ai_prior += 25  # boost — workflow files indicate AI flow, in-IDE attribution absent

# Cap and re-weight workflow file contribution
ai_score = (
    35 * explicit_ai
    + 10 * conv_rate
    + 10 * min(peak / 50, 1.0)
    + 20 * (1.0 if ai_workflow else 0.0)   # was 10 — bumped to 20
    + 5  * max(0, 1 - todo_per_kloc / 2)
    + 5  * min(doc_ratio, 1.0)
    + 10 * burstiness
    + 5  * msg_uniformity_excess
    + (25 if ide_copilot_signal else 0)
)
```

### Blend weight per axis

| Axis | v0 | v1 | Why |
|------|---:|---:|-----|
| ai | 0.5 | 0.5 | unchanged — still the most reliable evidence |
| author | 0.3 | **0.5** | new HHI-based prior is stronger; trust it more |
| team | 0.4 | **0.5** | same |
| research | 0.0 | **0.4** | new scaffold prior — moderate trust |
| unspecified | 0.0 | 0.0 | LLM-only |

## Next steps

1. Implement v1 changes in `collect/provenance.py` and `blend.py`
2. Re-run all 3 calibration repos
3. Compare against ground truth; iterate if drift remains
4. Lock in v1 once finna-app + mercurio + govtool all within ±15 per axis
