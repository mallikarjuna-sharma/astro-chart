import ast
from pathlib import Path

from Business_Prediction.business_determination.orchestration_services import (
    assess_evidence_sufficiency, finalize_result, validate_request,
)


PACKAGE = Path(__file__).parents[1] / "business_determination"


def test_internal_modules_forbid_wildcard_imports():
    violations = []
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
                violations.append((path.name, node.lineno))
    assert violations == []


def test_orchestration_services_are_independent_entry_points():
    assert callable(validate_request)
    assert callable(assess_evidence_sufficiency)
    assert callable(finalize_result)


def test_every_internal_module_parses_independently():
    for path in PACKAGE.glob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
