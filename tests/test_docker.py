from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.docker
def test_dockerfile_builds_and_runs_mcp_help() -> None:
    if os.environ.get("REMEMB_DOCKER_SMOKE") != "1":
        pytest.skip("Set REMEMB_DOCKER_SMOKE=1 to run the Docker registry smoke test")

    if shutil.which("docker") is None:
        pytest.skip("docker CLI is not available")

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
