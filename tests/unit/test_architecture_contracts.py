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


def _attr_chain(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [*_attr_chain(node.value), node.attr]
    if isinstance(node, ast.Call):
        return _attr_chain(node.func)
    return []


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


def test_domain_pipeline_policy_does_not_execute_port_io() -> None:
    """Domain may model routing, but it must not execute driven-port operations."""
    io_method_names = {
        "chat_completion",
        "chat_completion_stream",
        "check_availability",
        "check_connectivity",
        "execute_cypher",
        "fetch_all",
        "fetch_one",
        "health_check",
        "query",
        "query_stream",
        "transaction",
    }
    violations: list[str] = []

    for path in _python_files("domain"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in io_method_names:
                    violations.append(
                        f"{path.relative_to(SRC)} calls {node.func.attr} at line {node.lineno}"
                    )

    assert violations == []


def test_api_routers_do_not_call_container_ports_directly() -> None:
    """Routers should call use cases, not graph/vector/db/auth/LLM ports."""
    direct_ports = {"graph", "vector", "db", "auth", "llm", "embedding"}
    violations: list[str] = []

    for path in _python_files("api/routers"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            chain = _attr_chain(node)
            if node.attr not in direct_ports:
                continue
            if "container" in chain:
                violations.append(
                    f"{path.relative_to(SRC)} accesses container.{node.attr} at line {node.lineno}"
                )

    assert violations == []
