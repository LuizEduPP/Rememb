"""CLI for rememb - Launches TUI by default, MCP server available."""

from __future__ import annotations

import sys

import typer

from rememb import __version__
from rememb.store import SECTIONS
from rememb.utils import console, box, Columns, Panel, Table, Text


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
    cmd_table.add_row("rememb", "Launch interactive TUI")
    cmd_table.add_row("mcp", "Start MCP server for AI agents")
    cmd_table.add_row("fetch-model", "Download local embedding model for offline use")
    
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
    
    console.print("\n[dim]Tip: Run without arguments to start the interactive TUI.[/dim]\n")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool | None = typer.Option(
        None, "--version", "-v", callback=_version_callback, is_eager=True, help="Show version and exit."
    ),
) -> None:
    if ctx.invoked_subcommand is None:

        try:
            from rememb.tui import run_tui
            run_tui()
        except ImportError as e:
            print(f"Error loading TUI: {e}")
            _show_help()
            raise typer.Exit(1)


@app.command()
def mcp():
    """Start MCP server for AI agent integration."""
    import asyncio
    try:
        from rememb.mcp_server import run_server as mcp_run_server
        asyncio.run(mcp_run_server())
    except ImportError as e:
        print(f"MCP support requires additional dependencies: {e}")
        raise typer.Exit(1)

@app.command(name="fetch-model")
def fetch_model():
    """Download embedding model for offline semantic search."""
    console.print("Downloading [bold cyan]all-MiniLM-L6-v2[/bold cyan] (~80MB)...")
    
    try:
        from rich.progress import Progress, SpinnerColumn, TextColumn
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=False,
        ) as progress:
            progress.add_task(description="Downloading model weights from HuggingFace...", total=None)
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("all-MiniLM-L6-v2")
            console.print("[bold green]✓[/bold green] Model downloaded successfully.")
            console.print("[dim]You can now use semantic search offline.[/dim]")
    except ImportError:
        console.print("[bold red]Error:[/bold red] sentence-transformers not installed. Run: [cyan]pip install rememb[semantic][/cyan]")
        raise typer.Exit(1)
