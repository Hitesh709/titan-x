"""Fail-fast local production quality gates for Xecaps.

This deliberately delegates to the repository's existing toolchain instead of
introducing a second test framework or build system.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path = ROOT) -> None:
    print("==>", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def required(binary: str) -> str:
    path = shutil.which(binary)
    if not path:
        raise SystemExit(f"Required executable not found: {binary}")
    return path


def main() -> int:
    required("ruff")
    required("bandit")
    required("pip-audit")

    run(["ruff", "check", "src", "tests"])
    run(["ruff", "format", "--check", "src", "tests"])
    run(["bandit", "-q", "-r", "src"])
    run(["pip-audit"])

    web = ROOT / "web"
    if web.exists() and (web / "package.json").exists():
        npm = "npm.cmd" if sys.platform == "win32" else "npm"
        required(npm)
        run([npm, "run", "typecheck"], cwd=web)
        run([npm, "run", "build"], cwd=web)

    print("All Xecaps production quality gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
