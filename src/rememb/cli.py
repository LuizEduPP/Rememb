"""rememb CLI — persistent memory for AI agents."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich import box

from rememb import __version__
from rememb.store import (
    SECTIONS,
    find_root,
    init,
    is_initialized,
    read_entries,
    search_entries,
    write_entry,
)

app = typer.Typer(
    name="rememb",
    help="Persistent memory for AI agents — local, portable, zero config.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()


def _root() -> Path:
    return find_root()


@app.command()
def version():
    """Show rememb version."""
    console.print(f"rememb v{__version__}")


@app.command()
def init_cmd(
    path: Optional[Path] = typer.Argument(None, help="Project root (default: current dir)"),
    name: str = typer.Option("", "--name", "-n", help="Project name"),
):
    """Initialize .rememb/ in the current project."""
    root = (path or Path.cwd()).resolve()

    if is_initialized(root):
        console.print(f"[yellow]Already initialized at {root / '.rememb'}[/yellow]")
        raise typer.Exit()

    rememb = init(root, project_name=name)
    console.print(Panel(
        f"[green]✓[/green] Initialized [bold].rememb/[/bold] at [dim]{rememb}[/dim]\n\n"
        f"[dim]Sections:[/dim] {', '.join(SECTIONS)}\n\n"
        f"Next steps:\n"
        f"  [bold]rememb write[/bold] --section project \"My project does X\"\n"
        f"  [bold]rememb read[/bold]\n"
        f"  [bold]rememb rules[/bold]  ← copy rules for your AI editor",
        title="rememb",
        border_style="green",
    ))


app.command("init")(init_cmd)


@app.command()
def write(
    content: str = typer.Argument(..., help="Memory content to store"),
    section: str = typer.Option("context", "--section", "-s", help=f"Section: {', '.join(SECTIONS)}"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Comma-separated tags"),
):
    """Write a new memory entry."""
    root = _root()
    tag_list = [t.strip() for t in tags.split(",")] if tags else []

    try:
        entry = write_entry(root, section, content, tag_list)
    except (RuntimeError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(
        f"[green]✓[/green] Saved [bold][{entry['section']}][/bold] "
        f"[dim]id={entry['id']} at {entry['created_at']}[/dim]"
    )


@app.command()
def read(
    section: Optional[str] = typer.Option(None, "--section", "-s", help="Filter by section"),
    raw: bool = typer.Option(False, "--raw", help="Output raw JSON"),
    agent: bool = typer.Option(False, "--agent", help="Output optimized for agent consumption"),
):
    """Read memory entries."""
    root = _root()

    try:
        entries = read_entries(root, section)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not entries:
        console.print("[dim]No entries found.[/dim]")
        raise typer.Exit()

    if raw:
        import json
        print(json.dumps(entries, indent=2))
        return

    if agent:
        _print_agent_format(entries)
        return

    _print_table(entries)


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    top_k: int = typer.Option(5, "--top", "-k", help="Number of results"),
    agent: bool = typer.Option(False, "--agent", help="Output optimized for agent consumption"),
):
    """Search memory entries semantically (falls back to keyword)."""
    root = _root()

    try:
        results = search_entries(root, query, top_k)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not results:
        console.print("[dim]No results found.[/dim]")
        raise typer.Exit()

    if agent:
        _print_agent_format(results)
        return

    console.print(f"\n[bold]Top {len(results)} results for:[/bold] [italic]{query}[/italic]\n")
    _print_table(results)


@app.command()
def rules(
    editor: Optional[str] = typer.Argument(None, help="Editor: windsurf, cursor, claude, continue, all"),
):
    """Print ready-to-use agent rules/instructions for your editor."""
    _rules = _build_rules()

    editors = {
        "windsurf": ("Windsurf / Cascade", "windsurf_rules"),
        "cursor": ("Cursor", "cursor_rules"),
        "claude": ("Claude / Claude.md", "claude_rules"),
        "continue": ("Continue.dev", "continue_rules"),
    }

    if editor and editor.lower() != "all" and editor.lower() in editors:
        label, key = editors[editor.lower()]
        console.print(Panel(_rules[key], title=f"Rules for {label}", border_style="cyan"))
        return

    for key, (label, rule_key) in editors.items():
        console.print(Panel(_rules[rule_key], title=f"Rules for {label}", border_style="cyan"))
        console.print()


def _build_rules() -> dict:
    base = (
        "# rememb — Agent Memory Rules\n\n"
        "At the START of every conversation:\n"
        "1. Run: `rememb read --agent` and absorb the memory context\n"
        "2. If searching for specific context: `rememb search \"<topic>\" --agent`\n\n"
        "At the END of every conversation (or when significant context is established):\n"
        "1. Run: `rememb write \"<summary>\" --section <section>`\n"
        "   Sections: project | actions | systems | requests | user | context\n\n"
        "Rules:\n"
        "- Always read memory before acting on a new session\n"
        "- Always write memory after learning something important about the project or user\n"
        "- Keep entries concise (1-3 sentences max per entry)\n"
        "- Tag entries when relevant: `--tags tag1,tag2`\n"
    )

    windsurf = (
        base +
        "\n# Windsurf specific:\n"
        "- Place this in: Settings → Cascade → Custom Instructions\n"
        "- Or in: .windsurfrules file at project root\n"
    )

    cursor = (
        base +
        "\n# Cursor specific:\n"
        "- Place this in: .cursorrules file at project root\n"
        "- Or in: Settings → Rules for AI\n"
    )

    claude = (
        base +
        "\n# Claude / CLAUDE.md specific:\n"
        "- Place this in: CLAUDE.md file at project root\n"
        "- Claude Code will automatically read CLAUDE.md\n"
    )

    continue_dev = (
        base +
        "\n# Continue.dev specific:\n"
        "- Place this in: .continuerc.json → systemMessage field\n"
        "- Or in: config.json → models[].systemMessage\n"
    )

    return {
        "windsurf_rules": windsurf,
        "cursor_rules": cursor,
        "claude_rules": claude,
        "continue_rules": continue_dev,
    }


def _print_table(entries: list[dict]) -> None:
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim", width=10)
    table.add_column("Section", style="bold", width=12)
    table.add_column("Content")
    table.add_column("Tags", style="dim", width=20)
    table.add_column("Date", style="dim", width=22)

    for e in entries:
        table.add_row(
            e["id"],
            e["section"],
            e["content"],
            ", ".join(e.get("tags", [])) or "-",
            e["created_at"],
        )

    console.print(table)


def _print_agent_format(entries: list[dict]) -> None:
    """Compact format optimized for LLM context consumption."""
    by_section: dict[str, list] = {}
    for e in entries:
        by_section.setdefault(e["section"], []).append(e)

    output = ["# Memory Context (rememb)\n"]
    for section, items in by_section.items():
        output.append(f"## {section.capitalize()}")
        for item in items:
            tags = f" [{', '.join(item['tags'])}]" if item.get("tags") else ""
            output.append(f"- {item['content']}{tags}")
        output.append("")

    print("\n".join(output))
