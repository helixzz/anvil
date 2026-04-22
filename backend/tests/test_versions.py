from __future__ import annotations

import tomllib
from pathlib import Path

import anvil


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
RUNNER_ROOT = REPO_ROOT / "runner"
FRONTEND_ROOT = REPO_ROOT / "frontend"


def _pyproject_version(root: Path) -> str:
    data = tomllib.loads((root / "pyproject.toml").read_text())
    return data["project"]["version"]


def _frontend_version() -> str:
    import json

    return json.loads((FRONTEND_ROOT / "package.json").read_text())["version"]


def test_backend_dunder_matches_pyproject() -> None:
    assert anvil.__version__ == _pyproject_version(BACKEND_ROOT)


def test_runner_pyproject_matches_backend() -> None:
    assert _pyproject_version(RUNNER_ROOT) == _pyproject_version(BACKEND_ROOT)


def test_frontend_package_version_matches_backend() -> None:
    assert _frontend_version() == _pyproject_version(BACKEND_ROOT)
