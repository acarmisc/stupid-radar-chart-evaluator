# govtool — Ground Truth

**Source repo**: `/Users/andrea/Projects/abstract-ces/govtool`
**Labelled by**: owner ("almost entirely vibe-coded")
**Date**: 2026-05-28

## Expected scores

| Axis | Expected | Rationale |
|------|---------:|-----------|
| author | 25-40 | Single primary human (Riccardo) but heavily AI-assisted |
| **ai** | **75-90** | Owner-confirmed "almost entirely vibe-coded"; 38% commits with `Co-Authored-By: Claude`; 46% commits from `*Agentic*` / `*Agent*` identities |
| team | 30-50 | Real humans: Riccardo + Abstract + Daniele + acarmisc; Riccardo dominates volume |
| research | 5-20 | Domain-specific allocation/scheduling code; little tutorial scaffold |
| unspecified | 0-10 | Clear provenance throughout |

## Observed deterministic signals

- 907 total commits
- 38% with `Co-Authored-By: Claude` footer
- 46% from agentic-named authors (`Riccardo Agentic`, `RiccardoAgent`)
- 79% conventional-commit compliance
- 18% inter-commit gaps ≤ 60s (burstiness)
- 108 commits on peak day
- 1 TODO marker in 45 000 LOC
- doc/code ratio: 0.24
- `CLAUDE.md` + `docs/AGENTS.md` present

## Notes

This is a **cyborg repo** — single human + heavy AI. Expect `author` low but not zero (the human shape is real), `ai` very high, `team` moderate (real but concentrated).
