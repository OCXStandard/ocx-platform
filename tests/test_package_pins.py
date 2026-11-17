"""Inter-package pins must admit the current version of each workspace member."""
from pathlib import Path

import pytest
import tomllib
from packaging.requirements import Requirement

PACKAGES = Path(__file__).resolve().parents[1] / "packages"


def _projects() -> dict[str, dict]:
    return {
        p.parent.name: tomllib.loads(p.read_text(encoding="utf-8"))["project"]
        for p in sorted(PACKAGES.glob("*/pyproject.toml"))
    }


def _pins():
    projects = _projects()
    versions = {proj["name"]: proj["version"] for proj in projects.values()}
    for proj in projects.values():
        for dep in proj.get("dependencies", []):
            req = Requirement(dep)
            if req.name in versions:
                yield proj["name"], req, versions[req.name]


@pytest.mark.parametrize("owner,req,current", list(_pins()),
                         ids=lambda v: str(v) if isinstance(v, str) else None)
def test_workspace_pin_admits_current_version(owner, req, current):
    assert req.specifier.contains(current, prereleases=True), (
        f"{owner} pins {req} but {req.name} is {current}")
