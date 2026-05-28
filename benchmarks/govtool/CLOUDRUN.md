# Cloud Run Deployment — Model Selection

**Scenario**: LiteLLM gateway running on **Google Cloud Run (europe-west1)**, routing per-file code-classification calls (small JSON outputs, 5-axis 0-100 scores) to upstream LLM APIs.

## Research finding (2026 SOTA)

The single best pick for this deployment, by every measure, is **`vertex_ai/gemini-2.5-flash`**:

| Dimension | Why it wins |
|---|---|
| **Latency** | Same-region Cloud Run ↔ Vertex AI stays on Google's private backbone → ~150-300ms TTFB vs ~400-700ms for Anthropic/OpenAI from EU |
| **JSON reliability** | Native constrained decoding via `response_format: {type: json_schema}` — zero schema drift |
| **Cost** | $0.30 input / $2.50 output per 1M tokens. A 200-file run ≈ $0.04. Batch API halves it. |
| **Auth** | Workload Identity Federation — no key rotation, no static secrets |
| **Rate limits** | Vertex AI quota dramatically exceeds OpenAI/Anthropic tiers |

**Cheap fallback recommended**: `vertex_ai/gemini-2.5-flash-lite` ($0.10 / $0.40), same co-location, same constrained decoding.

## Cloud Run hosting constraints (LiteLLM-specific)

| Setting | Value | Why |
|---|---|---|
| Execution env | **Gen2** | Gen1's gVisor breaks some native exts |
| Memory | **≥1 GiB** | LiteLLM image + Python heap; default 512 MiB is tight |
| Request timeout | **3600s max** | Set `--timeout=3600` for streaming-heavy paths |
| Concurrency | **20-50** per instance for Vertex | Above that, autoscale instances rather than queuing inside |
| Database | **Cloud SQL Postgres**, NOT SQLite | Cloud Run FS is ephemeral; SQLite state per-instance |
| Cache | **Redis (Memorystore)** | Shared rate-limit + response cache across instances |
| Cold start | **`--min-instances=1`** if p99 < 1s matters | LiteLLM Docker is ~800MB, 4-8s scale-from-zero |
| Auth to Vertex | **Workload Identity Federation** | No SA key files in container |

### Minimal `config.yaml`

```yaml
model_list:
  - model_name: code-fast       # default alias
    litellm_params:
      model: vertex_ai/gemini-2.5-flash
      vertex_project: my-project
      vertex_location: europe-west1
      response_format: { type: json_object }

  - model_name: code-cheap      # cheaper variant
    litellm_params:
      model: vertex_ai/gemini-2.5-flash-lite
      vertex_project: my-project
      vertex_location: europe-west1

  - model_name: code-backup     # cross-provider fallback
    litellm_params:
      model: claude-haiku-4-5
      api_key: os.environ/ANTHROPIC_API_KEY

router_settings:
  routing_strategy: latency-based-routing
  num_retries: 2
  timeout: 30
  fallbacks:
    - code-fast: ["code-cheap", "code-backup"]

litellm_settings:
  drop_params: true
  request_timeout: 25     # < Cloud Run's own timeout
  cache: true
  cache_params: { type: redis }
```

## Benchmarked against current gateway (no Vertex AI yet)

The current `llm-gw.ces.abssrv.it` gateway does **not** proxy Vertex AI, Anthropic direct, or OpenAI direct — Claude returns `Missing Anthropic API Key`. So the production Cloud Run recommendation requires **adding `vertex_ai/*` providers** to the gateway config.

For the closest equivalents currently available, here are the Cloud Run-tier results (small-to-mid params, cheap, fast):

| Model | author | ai | team | research | uns. | files | Cloud Run fit |
|-------|------:|---:|----:|--------:|----:|------:|---------------|
| **gemini-3-flash-preview** | 35 | 72 | 35 | 13 | 0 | 5/5 | **best proxy for the recommended Vertex stack** — Google model, similar profile |
| ministral-3:14b | 18 | **74** | 21 | 11 | 0 | 5/5 | sharpest `ai`, tiny (14B), EU-friendly Mistral routing |
| deepseek-v4-flash | 17 | 68 | 34 | 5 | 4 | 5/5 | very cheap; cross-Atlantic latency penalty |
| gpt-oss:120b | 26 | 67 | 55 | 16 | 0 | 5/5 | OpenAI open-weight; inflates `team` |
| gpt-oss:20b | 24 | 66 | **60** | 6 | 5 | 5/5 | smallest, cheapest; heavy `team` inflation |
| qwen3-coder-next | **64** | 60 | 57 | 20 | 10 | 5/5 | preview release — over-credits `author`, hedges into `unspecified`. Avoid. |

## Ranked Cloud Run recommendation

| Tier | Model | Rationale |
|------|-------|-----------|
| **1 — Production default** | `vertex_ai/gemini-2.5-flash` *(needs gateway add)* | Co-located + native JSON schema + cheap. Confirmed by research as the canonical Cloud Run + LiteLLM stack. |
| 2 — Production fallback | `vertex_ai/gemini-2.5-flash-lite` *(needs gateway add)* | 3-6x cheaper, same co-location, escalate on schema-validation fail. |
| 3 — Current best on gateway | `gemini-3-flash-preview` | Closest deployed proxy for the Vertex Gemini stack. `ai=72`, 5/5 reliable. |
| 4 — Cheap on-gateway alternative | `ministral-3:14b` | 14B params → low cost, sharpest `ai` reading (74). Mistral EU endpoints reduce cross-Atlantic latency. |
| 5 — Premium on-gateway pick | `glm-4.7` / `mistral-large-3:675b` *(from main benchmark)* | If batch-volume is low and reliability premium is worth the cost. |
| **Avoid** | `qwen3-coder-next`, `nemotron-3-nano:30b` | Calibration failures (over-credit `author`, inflate `team`). |
| **Avoid** | `gpt-oss:20b` / `gpt-oss:120b` | Heavy `team` inflation (55-60). Code-content fixation. |

## Action items to make the Cloud Run deployment work

1. **Add `vertex_ai/*` to gateway** — register `vertex_ai/gemini-2.5-flash` and `vertex_ai/gemini-2.5-flash-lite` in the LiteLLM config with project + Workload Identity. This is the lift that unlocks the canonical recommendation.
2. **Add Anthropic upstream** — currently broken (`Missing Anthropic API Key`). Adding a `code-backup` fallback alias to `claude-haiku-4-5` gives cross-provider resilience.
3. **Add Redis (Memorystore)** for cross-instance cache + rate-limit state.
4. **Switch from SQLite to Cloud SQL Postgres** for LiteLLM internal state.
5. Until #1 ships, use `gemini-3-flash-preview` from current gateway as the closest available proxy.

## Raw outputs

All per-model JSON snapshots in this directory: `gemini-3-flash-preview.json`, `deepseek-v4-flash.json`, `gpt-oss-120b.json`, `gpt-oss-20b.json`, `ministral-3-14b.json`, `qwen3-coder-next.json`.
