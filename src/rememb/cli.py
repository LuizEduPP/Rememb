from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.columns import Columns

from rememb import __version__
from rememb.store import (
    SECTIONS,
    clear_entries,
    delete_entry,
    edit_entry,
    find_root,
    format_entries,
    global_root,
    init,
    is_initialized,
    read_entries,
    search_entries,
    write_entry,
)

console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(Panel(
            f"[bold cyan]rememb[/bold cyan] [dim]v{__version__}[/dim]",
            border_style="cyan",
            padding=(0, 2)
        ))
        raise typer.Exit()


def _show_help():
    """Display custom styled help."""
    console.print()
    console.print(Panel(
        f"[bold cyan]rememb[/bold cyan] [dim]v{__version__}[/dim]\n"
        f"[dim italic]Persistent memory for AI agents — local, portable, zero config[/dim italic]",
        border_style="cyan",
        padding=(1, 2),
        title="🧠",
        title_align="left"
    ))
    
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


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None, "--version", "-v", callback=_version_callback, is_eager=True, help="Show version and exit."
    ),
) -> None:
    if ctx.invoked_subcommand is None:
        _show_help()
        raise typer.Exit()


def _root() -> Path:
    root = find_root()
    if not is_initialized(root):
        try:
            root = global_root()
            init(root, project_name="global", global_mode=True)
        except PermissionError as e:
            console.print(Panel(
                f"[red]✗ Permission denied[/red]\n"
                f"[dim]Cannot create ~/.rememb/ directory[/dim]\n"
                f"[dim]{e}[/dim]",
                border_style="red",
                padding=(0, 2)
            ))
            raise typer.Exit(1)
        except OSError as e:
            console.print(Panel(
                f"[red]✗ System error[/red]\n"
                f"[dim]Cannot initialize rememb storage[/dim]\n"
                f"[dim]{e}[/dim]",
                border_style="red",
                padding=(0, 2)
            ))
            raise typer.Exit(1)
    return root


@app.command("init")
def init_cmd(
    path: Optional[Path] = typer.Argument(None, help="Project root (default: current dir)"),
    name: str = typer.Option("", "--name", "-n", help="Project name"),
):
    root = (path or Path.cwd()).resolve()

    if is_initialized(root):
        console.print(Panel(
            f"[yellow]⚠ Already initialized[/yellow] at [dim]{root / '.rememb'}[/dim]",
            border_style="yellow",
            padding=(0, 2)
        ))
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
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Comma-separated tags"),
):
    root = _root()
    tag_list = [t.strip() for t in tags.split(",")] if tags else []

    try:
        entry = write_entry(root, section, content, tag_list)
    except (RuntimeError, ValueError) as e:
        console.print(Panel(
            f"[red]✗ Error[/red]\n[dim]{e}[/dim]",
            border_style="red",
            padding=(0, 2)
        ))
        raise typer.Exit(1)

    console.print(Panel(
        f"[green]✓[/green] Saved to [bold cyan]{entry['section']}[/bold cyan]\n"
        f"[dim]ID: {entry['id']} | {entry['created_at']}[/dim]",
        border_style="green",
        padding=(0, 2)
    ))


@app.command()
def read(
    section: Optional[str] = typer.Option(None, "--section", "-s", help="Filter by section"),
    raw: bool = typer.Option(False, "--raw", help="Output as JSON"),
    agent: bool = typer.Option(False, "--agent", help="Format for AI agents"),
):
    root = _root()

    try:
        entries = read_entries(root, section)
    except RuntimeError as e:
        console.print(Panel(
            f"[red]✗ Error[/red]\n[dim]{e}[/dim]",
            border_style="red",
            padding=(0, 2)
        ))
        raise typer.Exit(1)

    if not entries:
        console.print(Panel(
            "[dim]No entries found.[/dim]\n"
            "[dim italic]Use 'rememb write' to add memories[/dim italic]",
            border_style="dim",
            padding=(0, 2)
        ))
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

    try:
        results = search_entries(root, query, top_k)
    except RuntimeError as e:
        console.print(Panel(
            f"[red]✗ Error[/red]\n[dim]{e}[/dim]",
            border_style="red",
            padding=(0, 2)
        ))
        raise typer.Exit(1)

    if not results:
        console.print(Panel(
            "[dim]No results found.[/dim]",
            border_style="dim",
            padding=(0, 2)
        ))
        raise typer.Exit()

    if agent:
        _print_agent_format(results)
        return

    console.print(Panel(
        f"[bold]Top {len(results)} results[/bold] for: [italic yellow]{query}[/italic yellow]",
        border_style="cyan",
        padding=(0, 2)
    ))
    _print_table(results)


def _validate_entry_id(entry_id: str) -> bool:
    return bool(re.match(r"^[a-f0-9]{8}$", entry_id, re.IGNORECASE))


@app.command()
def delete(
    entry_id: str = typer.Argument(..., help="Entry ID (8 hex chars)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    if not _validate_entry_id(entry_id):
        console.print(Panel(
            f"[red]✗ Invalid entry ID format[/red]\n"
            f"[dim]{entry_id}[/dim]\n"
            f"[dim]Expected: 8 hexadecimal characters (e.g., a1b2c3d4)[/dim]",
            border_style="red",
            padding=(0, 2)
        ))
        raise typer.Exit(1)
    
    root = _root()
    if not yes:
        typer.confirm(f"Delete entry {entry_id}?", abort=True)
    if delete_entry(root, entry_id):
        console.print(Panel(
            f"[green]✓ Deleted[/green] entry [bold]{entry_id}[/bold]",
            border_style="green",
            padding=(0, 2)
        ))
    else:
        console.print(Panel(
            f"[red]✗ Not found[/red]\n[dim]ID: {entry_id}[/dim]",
            border_style="red",
            padding=(0, 2)
        ))
        raise typer.Exit(1)


@app.command()
def edit(
    entry_id: str = typer.Argument(..., help="Entry ID (8 hex chars)"),
    content: Optional[str] = typer.Option(None, "--content", "-c", help="Update content"),
    section: Optional[str] = typer.Option(None, "--section", "-s", help=f"Move to section: {', '.join(SECTIONS)}"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Replace tags (comma-separated)"),
):
    if not _validate_entry_id(entry_id):
        console.print(Panel(
            f"[red]✗ Invalid entry ID format[/red]\n"
            f"[dim]{entry_id}[/dim]\n"
            f"[dim]Expected: 8 hexadecimal characters (e.g., a1b2c3d4)[/dim]",
            border_style="red",
            padding=(0, 2)
        ))
        raise typer.Exit(1)
    
    if content is None and section is None and tags is None:
        console.print(Panel(
            "[red]✗ Error[/red]\n[dim]Provide at least one option: --content, --section, or --tags[/dim]",
            border_style="red",
            padding=(0, 2)
        ))
        raise typer.Exit(1)
    
    root = _root()
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    result = edit_entry(root, entry_id, content=content, section=section, tags=tag_list)
    if result:
        console.print(Panel(
            f"[green]✓ Updated[/green] entry [bold]{entry_id}[/bold]",
            border_style="green",
            padding=(0, 2)
        ))
        _print_table([result])
    else:
        console.print(Panel(
            f"[red]✗ Not found[/red]\n[dim]ID: {entry_id}[/dim]",
            border_style="red",
            padding=(0, 2)
        ))
        raise typer.Exit(1)


@app.command()
def clear(
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm deletion"),
):
    root = _root()
    entries = read_entries(root)
    if not entries:
        console.print(Panel(
            "[dim]No entries to clear.[/dim]",
            border_style="dim",
            padding=(0, 2)
        ))
        raise typer.Exit()
    
    console.print(Panel(
        f"[yellow]⚠ This will delete {len(entries)} entries[/yellow]",
        border_style="yellow",
        padding=(0, 2)
    ))
    _print_table(entries[:5])  
    if len(entries) > 5:
        console.print(Panel(
            f"[dim]... and {len(entries) - 5} more[/dim]",
            border_style="dim",
            padding=(0, 1)
        ))
    
    if not yes:
        console.print(Panel(
            "[dim]Use --yes to confirm deletion[/dim]",
            border_style="yellow",
            padding=(0, 2)
        ))
        raise typer.Exit()
    
    try:
        count = clear_entries(root, confirm=True)
        console.print(Panel(
            f"[green]✓ Cleared {count} entries[/green]",
            border_style="green",
            padding=(0, 2)
        ))
    except RuntimeError as e:
        console.print(Panel(
            f"[red]✗ Error[/red]\n[dim]{e}[/dim]",
            border_style="red",
            padding=(0, 2)
        ))
        raise typer.Exit(1)


@app.command("import")
def import_cmd(
    folder: Path = typer.Argument(..., help="Source folder"),
    section: str = typer.Option("context", "--section", "-s", help=f"Target section: {', '.join(SECTIONS)}"),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Include subfolders"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview only"),
):
    root = _root()
    folder = folder.expanduser().resolve()

    if not folder.exists():
        console.print(Panel(
            f"[red]✗ Folder not found[/red]\n[dim]{folder}[/dim]",
            border_style="red",
            padding=(0, 2)
        ))
        raise typer.Exit(1)

    pattern = "**/*" if recursive else "*"
    supported = {".md", ".txt", ".pdf"}
    files = [f for f in folder.glob(pattern) if f.is_file() and f.suffix.lower() in supported]

    if not files:
        console.print(Panel(
            f"[yellow]⚠ No supported files found[/yellow]\n[dim]{folder}[/dim]\n"
            f"[dim]Supported: .md, .txt, .pdf[/dim]",
            border_style="yellow",
            padding=(0, 2)
        ))
        raise typer.Exit()

    console.print(Panel(
        f"[bold]Found {len(files)} files[/bold] in [dim]{folder}[/dim]",
        border_style="cyan",
        padding=(0, 2)
    ))

    imported = 0
    skipped = 0

    for f in files:
        content = _read_file_content(f)
        if not content or len(content.strip()) < 10:
            skipped += 1
            continue

        summary = _extract_summary(content)
        summary = summary.encode("utf-8", errors="ignore").decode("utf-8")
        entry_section = section

        if dry_run:
            console.print(f"  [dim]{escape(f.name)}[/dim] → [cyan]{entry_section}[/cyan]  {escape(summary[:80])}...")
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
        console.print(Panel(
            f"[green]✓ Imported {imported} files[/green], skipped [dim]{skipped}[/dim]",
            border_style="green",
            padding=(0, 2)
        ))
    else:
        console.print(Panel(
            "[dim]Dry run — nothing saved[/dim]\n"
            "[dim]Remove --dry-run to import[/dim]",
            border_style="dim",
            padding=(0, 2)
        ))


def _extract_summary(content: str) -> str:
    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            key, sep, value = line.partition(":")
            if not sep:
                continue
            v = value.strip()
            if len(v) > 20 and " " in v:
                return v
        content = content[fm_match.end():].strip()

    skip = re.compile(r"^(#+\s|[-*+]\s|>\s|```|\s*$|\S+:\s)", re.IGNORECASE)
    lines = []
    for line in content.splitlines():
        if skip.match(line):
            if lines:
                break
            continue
        lines.append(line.strip())
        if len(" ".join(lines)) >= 300:
            break

    if lines:
        return " ".join(lines)[:500]
    return content.strip()[:500].replace("\n", " ").strip()


def _read_file_content(path: Path) -> str:
    if path.suffix.lower() in {".md", ".txt"}:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError, PermissionError) as e:
            console.print(Panel(
                f"[yellow]⚠ Could not read {path.name}[/yellow]\n[dim]{e}[/dim]",
                border_style="yellow",
                padding=(0, 1)
            ))
            return ""
    if path.suffix.lower() == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            return " ".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            console.print(Panel(
                "[yellow]⚠ PDF support requires:[/yellow] pip install rememb[pdf]",
                border_style="yellow",
                padding=(0, 2)
            ))
            return ""
        except (OSError, PermissionError) as e:
            console.print(Panel(
                f"[yellow]⚠ Could not read PDF {path.name}[/yellow]\n[dim]{e}[/dim]",
                border_style="yellow",
                padding=(0, 1)
            ))
            return ""
        except Exception as e:
            console.print(Panel(
                f"[yellow]⚠ Could not parse PDF {path.name}[/yellow]\n[dim]{e}[/dim]",
                border_style="yellow",
                padding=(0, 1)
            ))
            return ""
    return ""



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
        console.print(Panel(
            "[red]✗ MCP support requires:[/red] pip install rememb[mcp]\n"
            f"[dim]{e}[/dim]",
            border_style="red",
            padding=(0, 2)
        ))
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


def _print_table(entries: list[dict]) -> None:
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan", show_lines=True)
    table.add_column("ID", style="dim", width=10)
    table.add_column("Section", style="bold", width=12)
    table.add_column("Content")
    table.add_column("Tags", style="dim", width=20)
    table.add_column("Date", style="dim", width=22)
    table.add_column("Updated", style="dim", width=22)

    for e in entries:
        table.add_row(
            e["id"],
            e["section"],
            escape(e["content"]),
            escape(", ".join(e.get("tags", [])) or "-"),
            e["created_at"],
            e.get("updated_at", "N/A"),
        )

    console.print(table)


def _print_agent_format(entries: list[dict]) -> None:
    print(format_entries(entries, include_id=False))
