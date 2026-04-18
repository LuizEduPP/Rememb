from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import typer

from rememb import __version__
from rememb.store import (
    SECTIONS,
    clear_entries,
    delete_entry,
    edit_entry,
    format_entries,
    get_stats,
    init,
    read_entries,
    search_entries,
    write_entry,
)
from rememb.utils import (
    box,
    Columns,
    console,
    escape,
    find_root,
    global_root,
    is_initialized,
    Panel,
    Table,
    _extract_summary,
    _handle_error,
    _parse_tags,
    _print_error,
    _print_info,
    _print_success,
    _print_table,
    _print_warning,
    _read_file_content,
    _root,
    _validate_entry_id_or_exit,
)


def _version_callback(value: bool) -> None:
    if value:
        console.print(Panel(
            f"[bold cyan]rememb[/bold cyan] [dim]v{__version__}[/dim]",
            border_style="cyan",
            padding=(0, 2)
        ))
        raise typer.Exit()


class CustomTyper(typer.Typer):
    def __call__(self, *args, **kwargs):
        if len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1] in ("--help", "-h")):
            _show_help()
            sys.exit(0)
        return super().__call__(*args, **kwargs)


app = CustomTyper(
    name="rememb",
    help="Persistent memory for AI agents — local, portable, zero config.",
    no_args_is_help=False,
    rich_markup_mode="rich",
)


def _show_help():
    console.print(f"\n[bold bright_cyan]rememb[/bold bright_cyan] [dim]v{__version__}[/dim]")
    console.print(f"[dim]Persistent memory for AI agents — local, portable, zero config.[/dim]\n")
    
    # Commands section
    console.print(f"\n[bold bright_cyan]Commands[/bold bright_cyan]")
    
    commands = [
        ("init", "Initialize memory store in current directory"),
        ("write", "Save a new memory entry"),
        ("read", "Display all stored memories"),
        ("search", "Search memories by content or tags"),
        ("edit", "Update an existing memory entry"),
        ("delete", "Remove a memory entry"),
        ("clear", "Remove all memory entries"),
        ("import", "Import files into memory"),
        ("stats", "Show memory statistics"),
        ("rules", "Print AI agent rules"),
        ("mcp", "Start MCP server"),
    ]
    
    cmd_table = Table(box=None, show_header=False, padding=(0, 2))
    cmd_table.add_column(style="bold green", width=12)
    cmd_table.add_column(style="dim")
    
    for cmd, desc in commands:
        cmd_table.add_row(cmd, desc)
    
    console.print(cmd_table)
    
    # Options section
    console.print(f"\n[bold bright_cyan]Options[/bold bright_cyan]")
    
    opts_table = Table(box=None, show_header=False, padding=(0, 2))
    opts_table.add_column(style="bold yellow", width=12)
    opts_table.add_column(style="dim", width=6)
    opts_table.add_column(style="dim")
    
    opts_table.add_row("--version", "-v", "Show version and exit")
    opts_table.add_row("--help", "-h", "Show this help message")
    
    console.print(opts_table)
    
    # Sections info
    console.print(f"\n[bold bright_cyan]Sections[/bold bright_cyan] [dim](use with --section)[/dim]")
    
    sections_cols = Columns([
        f"[bold]{s}[/bold]" for s in SECTIONS
    ], equal=True, expand=False)
    console.print(sections_cols)
    
    # Examples
    console.print(f"\n[bold bright_cyan]Examples[/bold bright_cyan]")
    console.print(f"  [dim]$[/dim] [green]rememb[/green] [cyan]init[/cyan]")
    console.print(f"  [dim]$[/dim] [green]rememb[/green] [cyan]write[/cyan] [yellow]\"Project uses FastAPI\"[/yellow] [cyan]--section[/cyan] project")
    console.print(f"  [dim]$[/dim] [green]rememb[/green] [cyan]search[/cyan] [yellow]\"database\"[/yellow]")
    console.print(f"  [dim]$[/dim] [green]rememb[/green] [cyan]read[/cyan] [cyan]--agent[/cyan]")
    
    console.print()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool | None = typer.Option(
        None, "--version", "-v", callback=_version_callback, is_eager=True, help="Show version and exit."
    ),
) -> None:
    if ctx.invoked_subcommand is None:
        _show_help()
        raise typer.Exit()


@app.command("init")
def init_cmd(
    path: Path | None = typer.Argument(None, help="Project root (default: current dir)"),
    name: str = typer.Option("", "--name", "-n", help="Project name"),
):
    root = (path or Path.cwd()).resolve()

    if is_initialized(root):
        _print_warning(f"Already initialized at [dim]{root / '.rememb'}[/dim]")
        raise typer.Exit()

    global_mode = root == global_root()
    rememb = init(root, project_name=name, global_mode=global_mode)
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





@app.command()
def write(
    content: str = typer.Argument(..., help="Content to store"),
    section: str = typer.Option("context", "--section", "-s", help=f"Section: {', '.join(SECTIONS)}"),
    tags: str | None = typer.Option(None, "--tags", "-t", help="Comma-separated tags"),
    skip_duplicates: bool = typer.Option(False, "--skip-duplicates", help="Skip duplicate entries"),
):
    root = _root()
    tag_list = _parse_tags(tags) or []

    entry = _handle_error(write_entry, root, section, content, tag_list, skip_duplicates)
    _print_success(f"Saved to [bold cyan]{entry['section']}[/bold cyan]\n[dim]ID: {entry['id']} | {entry['created_at']}[/dim]")


@app.command()
def read(
    section: str | None = typer.Option(None, "--section", "-s", help="Filter by section"),
    raw: bool = typer.Option(False, "--raw", help="Output as JSON"),
    agent: bool = typer.Option(False, "--agent", help="Format for AI agents"),
):
    root = _root()

    entries = _handle_error(read_entries, root, section)
    if not entries:
        _print_warning("No entries found.\n[dim italic]Use 'rememb write' to add memories[/dim italic]", border_style="dim")
        raise typer.Exit()

    if raw:
        print(json.dumps(entries, indent=2))
        return

    if agent:
        _print_agent_format(entries)
        return

    _print_table(entries)


@app.command()
def search(
    query: str = typer.Argument(..., help="Search terms"),
    top_k: int = typer.Option(5, "--top", "-k", help="Max results"),
    agent: bool = typer.Option(False, "--agent", help="Format for AI agents"),
):
    root = _root()

    results = _handle_error(search_entries, root, query, top_k)
    if not results:
        _print_warning("No results found.", border_style="dim")
        raise typer.Exit()

    if agent:
        _print_agent_format(results)
        return

    _print_info(f"Top {len(results)} results for: [italic yellow]{query}[/italic yellow]")
    _print_table(results)


@app.command()
def delete(
    entry_id: str = typer.Argument(..., help="Entry ID (8 hex chars)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    _validate_entry_id_or_exit(entry_id)
    
    root = _root()
    if not yes:
        typer.confirm(f"Delete entry {entry_id}?", abort=True)
    if delete_entry(root, entry_id):
        _print_success(f"Deleted entry [bold]{entry_id}[/bold]")
    else:
        _print_error(f"Not found\n[dim]ID: {entry_id}[/dim]")
        raise typer.Exit(1)


@app.command()
def edit(
    entry_id: str = typer.Argument(..., help="Entry ID (8 hex chars)"),
    content: str | None = typer.Option(None, "--content", "-c", help="Update content"),
    section: str | None = typer.Option(None, "--section", "-s", help=f"Move to section: {', '.join(SECTIONS)}"),
    tags: str | None = typer.Option(None, "--tags", "-t", help="Replace tags (comma-separated)"),
):
    _validate_entry_id_or_exit(entry_id)
    
    if content is None and section is None and tags is None:
        _print_error("Provide at least one option: --content, --section, or --tags")
        raise typer.Exit(1)
    
    root = _root()
    tag_list = _parse_tags(tags)
    result = edit_entry(root, entry_id, content=content, section=section, tags=tag_list)
    if result:
        _print_success(f"Updated entry [bold]{entry_id}[/bold]")
        _print_table([result])
    else:
        _print_error(f"Not found\n[dim]ID: {entry_id}[/dim]")
        raise typer.Exit(1)


@app.command()
def clear(
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm deletion"),
):
    root = _root()
    entries = read_entries(root)
    if not entries:
        _print_warning("No entries to clear.", border_style="dim")
        raise typer.Exit()
    
    _print_warning(f"This will delete {len(entries)} entries")
    _print_table(entries[:5])  
    if len(entries) > 5:
        _print_warning(f"... and {len(entries) - 5} more", border_style="dim")
    
    if not yes:
        _print_warning("Use --yes to confirm deletion")
        raise typer.Exit()
    
    count = _handle_error(clear_entries, root, confirm=True)
    _print_success(f"Cleared {count} entries")


@app.command("import")
def import_cmd(
    folder: Path = typer.Argument(..., help="Source folder"),
    section: str = typer.Option("context", "--section", "-s", help=f"Target section: {', '.join(SECTIONS)}"),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Include subfolders"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview only"),
):
    root = _root()
    folder = folder.expanduser().resolve()

    # Validate folder is within project root or current working directory
    try:
        folder.relative_to(root)
    except ValueError:
        try:
            cwd = Path.cwd().resolve()
            folder.relative_to(cwd)
        except ValueError:
            _print_error(f"Path traversal detected\n[dim]{folder}\n[dim]Folder must be within project or current directory[/dim]")
            raise typer.Exit(1)

    if not folder.exists():
        _print_error(f"Folder not found\n[dim]{folder}[/dim]")
        raise typer.Exit(1)

    pattern = "**/*" if recursive else "*"
    supported = {".md", ".txt", ".pdf"}
    files = [f for f in folder.glob(pattern) if f.is_file() and f.suffix.lower() in supported]

    if not files:
        _print_warning(f"No supported files found\n[dim]{folder}\n[dim]Supported: .md, .txt, .pdf[/dim]")
        raise typer.Exit()

    _print_info(f"Found {len(files)} files in [dim]{folder}[/dim]")

    imported = 0
    skipped = 0

    for f in files:
        content = _read_file_content(f)
        if not content:
            skipped += 1
            continue

        summary = _extract_summary(content)
        summary = summary.encode("utf-8", errors="ignore").decode("utf-8")
        entry_section = section

        if dry_run:
            console.print(f"  [dim]{escape(f.name)}[/dim] → [cyan]{entry_section}[/cyan]  {escape(summary)}...")
        else:
            try:
                write_entry(root, entry_section, f"{f.stem}: {summary}", tags=[f.suffix.lstrip(".")])
                console.print(f"  [green]✓[/green] {f.name} → [{entry_section}]")
                imported += 1
            except (RuntimeError, ValueError, TypeError) as e:
                console.print(f"  [red]✗[/red] {f.name}: {e}")
                skipped += 1
            except OSError as e:
                console.print(f"  [red]✗[/red] {f.name}: I/O error - {e}")
                skipped += 1

    if not dry_run:
        _print_success(f"Imported {imported} files, skipped [dim]{skipped}[/dim]")
    else:
        _print_warning("Dry run — nothing saved\n[dim]Remove --dry-run to import[/dim]", border_style="dim")



@app.command()
def stats():
    """Show memory statistics."""
    root = find_root()
    s = get_stats(root)

    if s["total"] == 0:
        _print_warning("No entries found. Run [bold]rememb init[/bold] to get started.", border_style="dim")
        return

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column(style="dim", width=16)
    table.add_column(style="bold")

    table.add_row("Total entries", str(s["total"]))
    table.add_row("Memory size", f"{s['size_kb']} KB")
    table.add_row("Oldest entry", s["oldest"])
    table.add_row("Newest entry", s["newest"])
    table.add_row("", "")
    for sec in SECTIONS:
        count = s["by_section"][sec]
        bar = "█" * count
        table.add_row(sec, f"{bar}  {count}")

    console.print(Panel(
        table,
        title="[bold cyan]rememb stats[/bold cyan]",
        border_style="cyan",
        padding=(0, 1)
    ))


@app.command()
def rules():
    """Print generic rules for AI agents."""
    print(GENERIC_RULES)


@app.command()
def mcp():
    import asyncio
    try:
        from rememb.mcp_server import run_server as mcp_run_server
        asyncio.run(mcp_run_server())
    except ImportError as e:
        _print_error(f"MCP support requires: pip install rememb[mcp]\n[dim]{e}[/dim]")
        raise typer.Exit(1)


GENERIC_RULES = """# rememb

You have access to `rememb`, a CLI tool for persistent memory across sessions.
Use it to remember and retrieve context about this project and user.

## Reading memory
Run `rememb read --agent` to load all stored context before responding.
Run `rememb search "<topic>" --agent` to find specific information.

## Writing memory
Run `rememb write "<summary>" --section <section>` when you learn something worth remembering.
Available sections: project | actions | systems | requests | user | context

## Editing memory
Run `rememb edit <id> --content "<new content>"` to update an entry.
Run `rememb edit <id> --section <section>` to move an entry to another section.
Run `rememb delete <id> --yes` to remove an entry.
Run `rememb clear --yes` to remove all entries (use with caution).

## Rules
- Always read memory at the start of a new session
- Save important context after learning it — do not wait
- Keep entries short (1-3 sentences)
- Use --tags to categorize: `rememb write "..." --section project --tags tag1,tag2`

## Importing files
If the user asks to import notes or files into rememb:
1. Run `rememb import <folder> --dry-run` to preview files
2. Decide which section fits the content
3. Run `rememb import <folder> --section <section>` to save
4. For mixed content, read individual files and use `rememb write` instead
"""


def _print_agent_format(entries: list[dict]) -> None:
    print(format_entries(entries, include_id=False))
