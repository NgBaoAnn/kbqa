"""Architecture contract tests for the Clean Architecture src layout."""

from __future__ import annotations

import ast
from pathlib import Path


SRC = Path(__file__).resolve().parents[2] / "src"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _python_files(package: str) -> list[Path]:
    return list((SRC / package).rglob("*.py"))


def test_dependency_direction_points_inward() -> None:
    rules = {
        "domain": ("api", "adapters", "use_cases", "ports"),
        "ports": ("api", "adapters", "use_cases"),
        "use_cases": ("api", "adapters"),
        "adapters": ("api", "use_cases"),
    }
    violations: list[str] = []

    for package, forbidden_roots in rules.items():
        for path in _python_files(package):
            for imported in _imports(path):
                root = imported.split(".", 1)[0]
                if root in forbidden_roots:
                    violations.append(f"{path.relative_to(SRC)} imports {imported}")

    assert violations == []


def test_lightrag_concrete_adapter_does_not_leak_into_domain_or_use_cases() -> None:
    violations: list[str] = []
    for package in ("domain", "use_cases"):
        for path in _python_files(package):
            for imported in _imports(path):
                if imported == "lightrag" or imported.startswith(("lightrag.", "adapters.lightrag")):
                    violations.append(f"{path.relative_to(SRC)} imports {imported}")

    assert violations == []
