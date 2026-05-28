import pytest
from pydantic import ValidationError

from contrib_estimator.schema import AxisScores


def test_valid_scores():
    s = AxisScores(author=80, ai=40, team=90, research=55, unspecified=30)
    assert s.author == 80


def test_out_of_range_rejected():
    with pytest.raises(ValidationError):
        AxisScores(author=101, ai=0, team=0, research=0, unspecified=0)
    with pytest.raises(ValidationError):
        AxisScores(author=-1, ai=0, team=0, research=0, unspecified=0)
