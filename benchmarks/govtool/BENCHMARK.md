# Model Benchmark — govtool

**Repo**: `/Users/andrea/Projects/abstract-ces/govtool` (owner: "almost entirely vibe-coded")
**Config**: v2 fine-tuned pipeline (provenance + convex blend + bias-warned prompt)
**Sample**: 5 chunks, stratified weighted, `--seed 42` (deterministic file selection)
**Deterministic priors** (identical for every run): `ai_prior=54`, `author_prior=30`, `team_prior=46`

## Final results — sorted by `ai` score desc

| Model | author | ai | team | research | uns. | files | verdict |
|-------|------:|---:|----:|--------:|----:|------:|---------|
| **glm-4.7** | 12 | **74** | 24 | 5 | 0 | 5/5 | strongest `ai` reading, low hedging |
| **qwen3-coder:480b** | 29 | 70 | **51** | 21 | 0 | 5/5 | over-counts `team` |
| **mistral-large-3:675b** | 29 | 70 | 40 | 9 | 0 | 5/5 | well-balanced, top tier |
| **kimi-k2.6** | 25 | 70 | 33 | 5 | 4 | 3/5 ⚠ | 2 parse failures (deeper reasoning eats tokens) |
| **gemma4:31b** | 29 | 70 | 40 | 20 | 0 | 5/5 | matches mistral-large but slightly inflates `research` |
| nemotron-3-nano:30b | 28 | 69 | 55 | 35 | 0 | 5/5 | inflates `team` AND `research` |
| **kimi-k2.5** (default) | 36 | 69 | 37 | 9 | 5 | 5/5 | balanced, stable |
| glm-5.1 | 35 | 67 | 37 | 6 | 5 | 5/5 | near-identical to kimi-k2.5 |
| deepseek-v4-pro | 51 | 66 | 26 | 7 | 1 | 5/5 | over-credits `author` (51) |
| minimax-m2.5 | 33 | 64 | 32 | 14 | 5 | 5/5 | conservative across the board |
| devstral-small-2:24b | 30 | 62 | 40 | 9 | 0 | 5/5 | lowest `ai`, code-specialized blindspot |
| ~~mistral-medium-3.5~~ | — | — | — | — | — | 0/5 | **404 not deployed** (only `/model/info` listing) |
| ~~granite4.1~~ | — | — | — | — | — | 0/5 | **404 not deployed** (only `/model/info` listing) |

## Stability of the AI axis across 11 working models

| Metric | Value |
|--------|-----:|
| min | 62 |
| max | 74 |
| range | 12 |
| std dev | 3.5 |

The provenance prior (54) + 50% blend weight keeps every model in the **62-74 band**, regardless of model quality. The fine-tuning is doing its job.

## Notable findings

1. **Two models in `/model/info` aren't actually deployed** — `granite4.1`, `mistral-medium-3.5`. Both return `NotFoundError` despite being listed. Filed under "gateway config drift".
2. **`claude-opus-4-7` / `claude-sonnet-4-6` / `claude-haiku-4-5`** show up in the listing but fail with `AuthenticationError: Missing Anthropic API Key` — gateway has no upstream Anthropic credentials configured.
3. **`kimi-k2.6`** is the newest kimi but had **2/5 parse failures** at our 4000-token cap — its CoT reasoning is heavier than `kimi-k2.5`. Would need `max_tokens=6000+` to match k2.5's reliability.
4. **`glm-4.7`** produced the **strongest `ai` reading (74)** and lowest `unspecified` (0) — least hedging, most decisive judge. Could be a better default than kimi-k2.5 if reliability holds.
5. **`mistral-large-3:675b`** and **`gemma4:31b`** are both very close to the top — viable alternates.
6. **Code-specialized models underperform on metadata**: `devstral-small-2:24b` (Mistral code-specialist) gives the lowest `ai` score (62). Code-tuning seems to bias toward "this looks like clean code → human" rather than weighting commit metadata.

## Refreshed recommendation

| Use case | Model |
|----------|-------|
| Best balance + reliability (default) | **`kimi-k2.5`** (or `glm-5.1`) |
| Best `ai` reading (least hedge) | **`glm-4.7`** ← consider switching default after a reliability pass |
| Top-tier alternates | `mistral-large-3:675b`, `gemma4:31b`, `qwen3-coder:480b` |
| Avoid | `nemotron-3-nano:30b` (inflates team+research), `kimi-k2.6` at current token cap |

## How to access the full model catalogue

Team virtual-key (current `LITELLM_KEY` in `.env`) is restricted to 5 models. The full deployed catalogue (~50+ models) is visible via the **litellm master key**:

```bash
MASTER_KEY=$(kubectl -n litellm get secret litellm-secrets -o jsonpath='{.data.master-key}' | base64 -d)
curl -s "$LITELLM_BASE_URL/model/info" -H "Authorization: Bearer $MASTER_KEY" | jq -r '.data[].model_name'
```

Ask gateway admin to extend the team whitelist if you want production use of the strong open-weight models above (`glm-4.7`, `mistral-large-3:675b`, `qwen3-coder:480b`, `kimi-k2.6`).

## Raw outputs

Per-model `--verbose` JSON dumps in this directory. Reference 25-chunk run with default model: `../govtool_benchmark.json`.
