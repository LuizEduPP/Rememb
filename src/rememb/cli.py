"""CLI for rememb - Launches web UI by default, MCP server available."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from rememb import __version__
from rememb.config import DEFAULT_HOST, DEFAULT_SSE_PORT, DEFAULT_WEB_PORT
from rememb.hooks import HOOK_EVENTS
from rememb.install import HOSTS, run_install


console = Console()


def _version_callback(value: bool) -> None:
    if value:
        from rich.text import Text
        version_text = Text()
        version_text.append("🧠 ", style="bold bright_cyan")
        version_text.append("rememb\n", style="bold bright_cyan")
        version_text.append(f"v{__version__}", style="cyan")
        
        console.print(Panel(
            version_text,
            title="[bold cyan]Version[/bold cyan]",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 4),
            width=30
        ))
        console.print("[dim]Persistent memory for AI agents — local, portable, zero config.[/dim]\n")
        raise typer.Exit()


class CustomTyper(typer.Typer):
    def __call__(self, *args, **kwargs):
        if len(sys.argv) == 2 and sys.argv[1] in ("--help", "-h"):
            _show_help()
            sys.exit(0)
        return super().__call__(*args, **kwargs)


app = CustomTyper(
    name="rememb",
    help="Persistent memory for AI agents — local, portable, zero config.",
    no_args_is_help=False,
)


def _show_help():
    header_text = Text()
    header_text.append("🧠 ", style="bold bright_cyan")
    header_text.append("rememb\n", style="bold bright_cyan")
    header_text.append(f"v{__version__}", style="cyan")
    
    console.print(Panel(
        header_text,
        title="[bold cyan]rememb[/bold cyan]",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 4),
        width=30
    ))
    console.print("[dim italic]Persistent memory for AI agents — local, portable, zero config.[/dim italic]\n")
    
    cmd_table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan", border_style="green")
    cmd_table.add_column("Command", style="bold green", width=16)
    cmd_table.add_column("Description", style="white")
    cmd_table.add_row("rememb", "Launch web UI (opens in browser)")
    cmd_table.add_row("mcp", "Start MCP server (stdio or local SSE)")
    cmd_table.add_row("hook", "Host hooks: post-tool, stop, session-start")
    cmd_table.add_row("install", "Write MCP, rules, and hooks for an IDE")
    
    console.print(Panel(
        cmd_table,
        title="[bold green]:sparkles: Commands[/bold green]",
        border_style="green",
        box=box.ROUNDED,
        padding=(1, 2)
    ))
    
    opts_table = Table(box=box.ROUNDED, show_header=True, header_style="bold yellow", border_style="yellow")
    opts_table.add_column("Option", style="bold yellow", width=16)
    opts_table.add_column("Description", style="white")
    opts_table.add_row("--version, -v", "Show version and exit")
    opts_table.add_row("--help, -h", "Show this help message")
    
    console.print(Panel(
        opts_table,
        title="[bold yellow]:gear: Options[/bold yellow]",
        border_style="yellow",
        box=box.ROUNDED,
        padding=(1, 2)
    ))
    
    console.print("\n[dim]Tip: Run without arguments to open the web UI in your browser.[/dim]\n")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool | None = typer.Option(
        None, "--version", "-v", callback=_version_callback, is_eager=True, help="Show version and exit."
    ),
    host: str = typer.Option(DEFAULT_HOST, "--host", help="Host to bind the web UI server."),
    port: int = typer.Option(DEFAULT_WEB_PORT, "--port", min=1, max=65535, help="Port for the web UI server."),
    no_browser: bool = typer.Option(False, "--no-browser", help="Start server without opening the browser."),
) -> None:
    if ctx.invoked_subcommand is None:
        try:
            from rememb.web.app import run_web
            run_web(host=host, port=port, open_browser=not no_browser)
        except ImportError as e:
            print(f"Error loading web UI: {e}")
            _show_help()
            raise typer.Exit(1)


@app.command()
def mcp(
    transport: str = typer.Option(
        "stdio",
        "--transport",
        help="MCP transport to start: stdio or sse.",
    ),
    host: str = typer.Option(
        DEFAULT_HOST,
        "--host",
        help="Host for persistent SSE transport.",
    ),
    port: int = typer.Option(
        DEFAULT_SSE_PORT,
        "--port",
        min=1,
        max=65535,
        help="Port for persistent SSE transport.",
    ),
    project: list[Path] | None = typer.Option(
        None,
        "--project",
        "-P",
        help=(
            "Extra project root with its own .rememb store (repeatable). "
            "Global (~/.rememb) is always included."
        ),
        exists=False,
        file_okay=False,
        dir_okay=True,
        writable=False,
        resolve_path=False,
    ),
):
    """Start MCP server for AI agent integration."""
    import asyncio
    try:
        from rememb.mcp_server import run_server as mcp_run_server
        normalized_transport = transport.lower().strip()
        if normalized_transport not in {"stdio", "sse"}:
            typer.echo("Error: Unsupported transport. Use stdio or sse.", err=True)
            raise typer.Exit(1)

        if normalized_transport == "sse":
            if not sys.stdout.isatty():
                typer.echo(
                    "Error: SSE transport cannot be started through a stdio MCP client. "
                    f"Start `rememb mcp --transport sse --host {DEFAULT_HOST} --port {DEFAULT_SSE_PORT}` separately "
                    "and connect to the HTTP/SSE endpoint with a client that supports it.",
                    err=True,
                )
                raise typer.Exit(2)

            typer.echo(
                f"Starting persistent MCP SSE server at http://{host}:{port}",
                err=True,
            )
            typer.echo(
                "Connect clients to /sse and post messages to /messages/ to reuse this same process.",
                err=True,
            )

        asyncio.run(
            mcp_run_server(
                transport=normalized_transport,
                host=host,
                port=port,
                projects=project or [],
            )
        )
    except ImportError as e:
        print(f"MCP support requires additional dependencies: {e}")
        raise typer.Exit(1)


@app.command("hook")
def hook(
    event: str = typer.Argument(..., help=" | ".join(HOOK_EVENTS)),
) -> None:
    """Write or inject rememb memory from a host lifecycle event."""
    from rememb.hooks import run_hook

    code, out, err = run_hook(event, sys.stdin.read())
    if out:
        sys.stdout.write(out if out.endswith("\n") else f"{out}\n")
    if err:
        sys.stderr.write(err if err.endswith("\n") else f"{err}\n")
    raise typer.Exit(code)


@app.command("install")
def install(
    host: str | None = typer.Option(None, "--host", help=f"One of: {', '.join(HOSTS)}. Default: all."),
    apply: bool = typer.Option(False, "--apply", help="Write files. Without this flag, only print the plan."),
    project: bool = typer.Option(False, "--project", help="Write into the current directory instead of the user config."),
    uninstall: bool = typer.Option(False, "--uninstall", help="Remove only what rememb install wrote."),
) -> None:
    """Write MCP config, Memory Rules, and host hooks."""
    hosts = None
    if host:
        normalized = host.strip().lower()
        if normalized not in HOSTS:
            typer.echo(f"Error: unknown host {host!r}. Use {', '.join(HOSTS)}.", err=True)
            raise typer.Exit(1)
        hosts = [normalized]
    try:
        typer.echo(run_install(hosts, apply=apply, project=project, uninstall=uninstall))
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)
