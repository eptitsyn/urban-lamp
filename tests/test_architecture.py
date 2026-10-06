import ast
from pathlib import Path


def test_dependencies_point_inward() -> None:
    root = Path(__file__).resolve().parents[1] / "src/entity_marker"
    for layer, forbidden in (
        (
            "domain",
            (
                "entity_marker.infrastructure",
                "entity_marker.application",
                "entity_marker.cli",
                "typer",
                "pydantic",
            ),
        ),
        ("application", ("entity_marker.infrastructure", "entity_marker.cli", "typer", "pydantic")),
    ):
        for path in (root / layer).rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module]
                assert not any(module.startswith(forbidden) for module in modules), path
