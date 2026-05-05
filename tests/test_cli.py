from __future__ import annotations

import re

from typer.testing import CliRunner

from rememb import __version__
from rememb.cli import app


runner = CliRunner()


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_cli_version_reports_current_version():
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert f"v{__version__}" in result.stdout


def test_cli_help_lists_current_commands():
    result = runner.invoke(app, ["mcp", "--help"])
    output = _strip_ansi(result.stdout)

    assert result.exit_code == 0
    assert "--transport" in output
    assert "--host" in output
    assert "--port" in output


def test_cli_mcp_rejects_invalid_transport():
    result = runner.invoke(app, ["mcp", "--transport", "invalid"])

    assert result.exit_code == 1
    assert "Unsupported transport" in result.output