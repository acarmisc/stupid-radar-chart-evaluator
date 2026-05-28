"""Stratified weighted sampling. Keeps high-churn files when over budget."""
from __future__ import annotations

import random
from collections import defaultdict

from .collect.git import FileEntry


def stratify(files: list[FileEntry], max_chunks: int, seed: int) -> tuple[list[FileEntry], bool]:
    """Return (sampled_files, sampled_flag).

    Strategy:
      1. Group by top-level dir.
      2. Allocate per-stratum slots proportional to stratum total weight.
      3. Within stratum, weighted-sample by `churn_90d + 1`.
    """
    if len(files) <= max_chunks:
        return files, False

    rng = random.Random(seed)
    strata: dict[str, list[FileEntry]] = defaultdict(list)
    for f in files:
        top = f.rel.split("/", 1)[0] if "/" in f.rel else "."
        strata[top].append(f)

    stratum_weight = {k: sum(f.churn_90d + 1 for f in v) for k, v in strata.items()}
    total_weight = sum(stratum_weight.values()) or 1

    picked: list[FileEntry] = []
    for key, entries in strata.items():
        slots = max(1, round(max_chunks * stratum_weight[key] / total_weight))
        slots = min(slots, len(entries))
        weights = [f.churn_90d + 1 for f in entries]
        picked.extend(_weighted_sample_no_replace(entries, weights, slots, rng))

    # Trim if rounding overshot
    if len(picked) > max_chunks:
        rng.shuffle(picked)
        picked = picked[:max_chunks]
    return picked, True


def _weighted_sample_no_replace(items, weights, k, rng):
    """A-Res reservoir-style weighted sample without replacement."""
    keys = [(rng.random() ** (1.0 / max(w, 1e-9)), item) for w, item in zip(weights, items)]
    keys.sort(key=lambda kv: -kv[0])
    return [item for _, item in keys[:k]]
