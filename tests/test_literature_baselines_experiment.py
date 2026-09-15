from decimal import Decimal

from copromem.literature_baselines_experiment import extract_code, safe_execute_arithmetic


def test_restricted_arithmetic_execution() -> None:
    prediction, report = safe_execute_arithmetic("a = 12\nb = 3\nanswer = a / b")
    assert prediction == Decimal("4.0")
    assert report.startswith("Done")


def test_restricted_execution_rejects_unsafe_code() -> None:
    prediction, report = safe_execute_arithmetic("import os\nanswer = 1")
    assert prediction is None
    assert "only single-target assignments" in report


def test_extracts_fenced_code() -> None:
    assert extract_code("```python\nanswer = 7\n```") == "answer = 7"
