from contrib_estimator.aggregate import reduce_scores
from contrib_estimator.schema import AxisScores


def test_empty_returns_zeros():
    r = reduce_scores([])
    assert r.author == 0 and r.ai == 0 and r.team == 0 and r.research == 0 and r.unspecified == 0


def test_weighted_mean():
    a = AxisScores(author=100, ai=0, team=50, research=0, unspecified=0)
    b = AxisScores(author=0, ai=100, team=50, research=0, unspecified=0)
    # Equal weights → simple mean
    r = reduce_scores([(a, 10), (b, 10)])
    assert r.author == 50 and r.ai == 50 and r.team == 50


def test_weight_dominates():
    a = AxisScores(author=100, ai=0, team=0, research=0, unspecified=0)
    b = AxisScores(author=0, ai=0, team=0, research=0, unspecified=0)
    # a weighted 9x → mean close to 90
    r = reduce_scores([(a, 90), (b, 10)])
    assert r.author == 90
