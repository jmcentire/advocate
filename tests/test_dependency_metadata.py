"""Validate that shipped imports are represented in package metadata."""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())

# Distribution names do not always match their Python import package.
IMPORT_NAME_OVERRIDES = {
    "google-genai": {"google"},
    "pyyaml": {"yaml"},
}


def _distribution_name(requirement: str) -> str:
    return re.split(r"[\s\[<>=!~;]", requirement, maxsplit=1)[0].lower()


def _import_names(requirements: list[str]) -> set[str]:
    names: set[str] = set()
    for requirement in requirements:
        distribution = _distribution_name(requirement)
        names.add(distribution.replace("-", "_"))
        names.update(IMPORT_NAME_OVERRIDES.get(distribution, set()))
    return names


def _packaged_python_files() -> list[Path]:
    package_paths = PYPROJECT["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    return [
        python_file
        for package_path in package_paths
        for python_file in (ROOT / package_path).rglob("*.py")
    ]


def _module_imports(tree: ast.Module) -> set[str]:
    """Return imports executed while a module or class body is initialized."""
    imports: set[str] = set()

    def visit_statements(statements: list[ast.stmt]) -> None:
        for statement in statements:
            if isinstance(statement, ast.Import):
                imports.update(alias.name.partition(".")[0] for alias in statement.names)
            elif isinstance(statement, ast.ImportFrom) and statement.module:
                imports.add(statement.module.partition(".")[0])
            elif isinstance(statement, ast.ClassDef):
                visit_statements(statement.body)
            elif isinstance(statement, (ast.If, ast.For, ast.AsyncFor, ast.While)):
                visit_statements(statement.body)
                visit_statements(statement.orelse)
            elif isinstance(statement, (ast.With, ast.AsyncWith)):
                visit_statements(statement.body)
            elif isinstance(statement, ast.Try):
                visit_statements(statement.body)
                visit_statements(statement.orelse)
                visit_statements(statement.finalbody)
                for handler in statement.handlers:
                    visit_statements(handler.body)
            elif isinstance(statement, ast.Match):
                for case in statement.cases:
                    visit_statements(case.body)

    visit_statements(tree.body)
    return imports


def _all_imports(tree: ast.Module) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.partition(".")[0])
    return imports


def _third_party(imports: set[str]) -> set[str]:
    local_packages = {
        path.parts[0]
        for package_path in PYPROJECT["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
        for path in [Path(package_path).relative_to("src")]
    }
    return imports - sys.stdlib_module_names - local_packages - {"__future__"}


def test_runtime_imports_are_declared_dependencies() -> None:
    core_requirements = PYPROJECT["project"].get("dependencies", [])
    optional_groups = PYPROJECT["project"].get("optional-dependencies", {})
    optional_requirements = [
        requirement
        for requirements in optional_groups.values()
        for requirement in requirements
    ]
    core_imports = _import_names(core_requirements)
    all_declared_imports = core_imports | _import_names(optional_requirements)

    undeclared_eager: dict[str, set[str]] = {}
    undeclared_anywhere: dict[str, set[str]] = {}

    for python_file in _packaged_python_files():
        tree = ast.parse(python_file.read_text(), filename=str(python_file))
        relative_path = str(python_file.relative_to(ROOT))

        missing_eager = _third_party(_module_imports(tree)) - core_imports
        if missing_eager:
            undeclared_eager[relative_path] = missing_eager

        missing_anywhere = _third_party(_all_imports(tree)) - all_declared_imports
        if missing_anywhere:
            undeclared_anywhere[relative_path] = missing_anywhere

    assert not undeclared_eager, (
        "Imports executed during module initialization must be listed in "
        f"project.dependencies: {undeclared_eager}"
    )
    assert not undeclared_anywhere, (
        "Third-party imports must be listed in project.dependencies or an "
        f"optional dependency group: {undeclared_anywhere}"
    )
