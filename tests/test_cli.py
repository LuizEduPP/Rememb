from __future__ import annotations

from typer.testing import CliRunner

from rememb import __version__
from rememb.cli import app


runner = CliRunner()


def test_cli_version_reports_current_version():
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert f"v{__version__}" in result.stdout


def test_cli_help_lists_current_commands():
    result = runner.invoke(app, ["mcp", "--help"])

    assert result.exit_code == 0
    assert "--transport" in result.stdout
    assert "--host" in result.stdout
    assert "--port" in result.stdout


def test_cli_mcp_rejects_invalid_transport():
    result = runner.invoke(app, ["mcp", "--transport", "invalid"])

    assert result.exit_code == 1
    assert "Unsupported transport" in result.output