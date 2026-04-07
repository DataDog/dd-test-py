#!/usr/bin/env python3
"""Check that all dependencies in pyproject.toml are pinned to exact versions.

Runtime dependencies (under [project].dependencies) are allowed to use bounded
ranges (>=X,<Y) since this is a library. All other dependencies must use exact
pins (==X.Y.Z).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redefine]

# Sections where bounded ranges (>=, <) are acceptable (library runtime deps)
RUNTIME_ALLOWLIST_SECTIONS = frozenset({"project.dependencies"})

# Regex that matches a dependency pinned to an exact version with ==
EXACT_PIN_RE = re.compile(r"==\S+")

# Regex that detects unpinned or loosely-pinned version specifiers
LOOSE_SPECIFIERS_RE = re.compile(r"(>=|<=|~=|!=|>\s|<\s|\.\*)")


def _parse_deps(data: dict, path: str = "") -> list[tuple[str, str]]:
    """Walk the TOML structure and collect (section_path, dep_string) pairs."""
    results: list[tuple[str, str]] = []

    # [build-system].requires
    if "build-system" in data:
        for dep in data["build-system"].get("requires", []):
            results.append(("build-system.requires", dep))

    # [project].dependencies
    if "project" in data:
        for dep in data["project"].get("dependencies", []):
            results.append(("project.dependencies", dep))

    # [tool.hatch.envs.*].dependencies and extra-dependencies
    hatch_envs = data.get("tool", {}).get("hatch", {}).get("envs", {})
    for env_name, env_cfg in hatch_envs.items():
        if isinstance(env_cfg, dict):
            for dep in env_cfg.get("dependencies", []):
                results.append((f"tool.hatch.envs.{env_name}.dependencies", dep))
            for dep in env_cfg.get("extra-dependencies", []):
                results.append((f"tool.hatch.envs.{env_name}.extra-dependencies", dep))

    return results


def _check_dep(section: str, dep: str) -> str | None:
    """Return an error message if the dependency is not properly pinned."""
    # Runtime deps are allowed to use bounded ranges
    if section in RUNTIME_ALLOWLIST_SECTIONS:
        # They must still have *some* version constraint
        if not re.search(r"[><=~!]", dep):
            return f"  {section}: {dep!r} has no version constraint"
        return None

    # All other deps must use exact pins
    if EXACT_PIN_RE.search(dep):
        return None

    return f"  {section}: {dep!r} is not pinned to an exact version (use ==X.Y.Z)"


def main() -> int:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if not pyproject_path.exists():
        print(f"ERROR: {pyproject_path} not found")
        return 1

    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    deps = _parse_deps(data)
    errors: list[str] = []

    for section, dep in deps:
        err = _check_dep(section, dep)
        if err:
            errors.append(err)

    if errors:
        print("Unpinned dependencies found:")
        for err in errors:
            print(err)
        return 1

    print(f"All {len(deps)} dependencies are properly pinned.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
