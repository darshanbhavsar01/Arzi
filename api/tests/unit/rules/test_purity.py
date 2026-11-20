"""Architecture guard: the rules engine and domain stay pure.

Rupee maths must be reproducible from inputs alone, so these packages may not import I/O
layers, web frameworks or cloud SDKs. This test fails the build the moment one sneaks in.
"""

import ast
from pathlib import Path

import pytest

import arzi.domain
import arzi.rules

FORBIDDEN_PREFIXES = (
    "arzi.adapters",
    "arzi.api",
    "arzi.services",
    "arzi.agents",
    "arzi.observability",
    "fastapi",
    "starlette",
    "google",
    "httpx",
    "requests",
    "anyio",
    "asyncio",
    "socket",
    "os",
    "subprocess",
    "random",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def _is_forbidden(module: str) -> bool:
    return any(module == p or module.startswith(f"{p}.") for p in FORBIDDEN_PREFIXES)


@pytest.mark.parametrize("package", [arzi.rules, arzi.domain], ids=["rules", "domain"])
def test_pure_packages_import_no_io_layers(package: object) -> None:
    root = Path(str(getattr(package, "__file__", ""))).parent
    offenders = {
        f"{path.relative_to(root)}: {module}"
        for path in root.rglob("*.py")
        for module in _imports(path)
        if _is_forbidden(module)
    }

    assert not offenders, f"pure package imports I/O layers: {sorted(offenders)}"


@pytest.mark.parametrize(
    ("module", "forbidden"),
    [
        ("google.cloud.firestore", True),
        ("arzi.adapters.gcs", True),
        ("os", True),
        ("osmosis", False),
        ("decimal", False),
        ("arzi.domain.money", False),
    ],
)
def test_forbidden_prefix_matching(module: str, forbidden: bool) -> None:
    assert _is_forbidden(module) is forbidden
