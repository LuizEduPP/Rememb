from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def test_dockerfile_builds_and_runs_mcp_help() -> None:
    if shutil.which("docker") is None:
        return

    repo_root = Path(__file__).resolve().parents[1]
    image_tag = "rememb-ci-smoke:latest"

    build = subprocess.run(
        ["docker", "build", "-t", image_tag, str(repo_root)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, build.stderr

    run = subprocess.run(
        ["docker", "run", "--rm", image_tag, "rememb", "mcp", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    assert "--transport" in run.stdout

    subprocess.run(["docker", "image", "rm", "-f", image_tag], capture_output=True, check=False)
