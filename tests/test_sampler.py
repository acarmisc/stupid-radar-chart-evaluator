from pathlib import Path

from contrib_estimator.collect.git import FileEntry
from contrib_estimator.sampler import stratify


def _f(rel: str, churn: int) -> FileEntry:
    return FileEntry(path=Path(rel), rel=rel, size_bytes=100, churn_90d=churn)


def test_no_sample_when_under_cap():
    files = [_f(f"src/a{i}.py", i) for i in range(5)]
    out, sampled = stratify(files, max_chunks=10, seed=1)
    assert sampled is False
    assert len(out) == 5


def test_sample_respects_cap():
    files = [_f(f"src/a{i}.py", i) for i in range(50)] + [_f(f"tests/t{i}.py", i) for i in range(50)]
    out, sampled = stratify(files, max_chunks=20, seed=1)
    assert sampled is True
    assert len(out) <= 20


def test_stratification_covers_both_dirs():
    files = [_f(f"src/a{i}.py", 100) for i in range(50)] + [_f(f"tests/t{i}.py", 100) for i in range(50)]
    out, _ = stratify(files, max_chunks=10, seed=42)
    tops = {f.rel.split("/", 1)[0] for f in out}
    assert tops == {"src", "tests"}


def test_seed_reproducible():
    files = [_f(f"src/a{i}.py", i) for i in range(100)]
    a, _ = stratify(files, max_chunks=10, seed=7)
    b, _ = stratify(files, max_chunks=10, seed=7)
    assert [f.rel for f in a] == [f.rel for f in b]
