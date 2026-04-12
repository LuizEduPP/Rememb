from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich import box

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
        console.print(f"rememb v{__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="rememb",
    help="Persistent memory for AI agents — local, portable, zero config.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", "-V", callback=_version_callback, is_eager=True, help="Show version and exit."
    ),
) -> None:
    pass


def _root() -> Path:
    root = find_root()
    if not is_initialized(root):
        try:
            root = global_root()
            init(root, project_name="global", global_mode=True)
        except PermissionError as e:
            console.print(f"[red]Permission denied:[/red] Cannot create ~/.rememb/ directory")
            console.print(f"[dim]Details: {e}[/dim]")
            raise typer.Exit(1)
        except OSError as e:
            console.print(f"[red]System error:[/red] Cannot initialize rememb storage")
            console.print(f"[dim]Details: {e}[/dim]")
            raise typer.Exit(1)
    return root


@app.command()
def version():
    console.print(f"rememb v{__version__}")


@app.command("init")
def init_cmd(
    path: Optional[Path] = typer.Argument(None, help="Project root (default: current dir)"),
    name: str = typer.Option("", "--name", "-n", help="Project name"),
):
    root = (path or Path.cwd()).resolve()

    if is_initialized(root):
        console.print(f"[yellow]Already initialized at {root / '.rememb'}[/yellow]")
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
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(
        f"[green]✓[/green] Saved [bold][{entry['section']}][/bold] "
        f"[dim]id={entry['id']} at {entry['created_at']}[/dim]"
    )


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
    query: str = typer.Argument(..., help="Search terms"),
    top_k: int = typer.Option(5, "--top", "-k", help="Max results"),
    agent: bool = typer.Option(False, "--agent", help="Format for AI agents"),
):
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


def _validate_entry_id(entry_id: str) -> bool:
    return bool(re.match(r"^[a-f0-9]{8}$", entry_id, re.IGNORECASE))


@app.command()
def delete(
    entry_id: str = typer.Argument(..., help="Entry ID (8 hex chars)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    if not _validate_entry_id(entry_id):
        console.print(f"[red]Invalid entry ID format:[/red] {entry_id}")
        console.print("[dim]Expected: 8 hexadecimal characters (e.g., a1b2c3d4)[/dim]")
        raise typer.Exit(1)
    
    root = _root()
    if not yes:
        typer.confirm(f"Delete entry {entry_id}?", abort=True)
    if delete_entry(root, entry_id):
        console.print(f"[green]✓ Deleted[/green] {entry_id}")
    else:
        console.print(f"[red]Not found:[/red] {entry_id}")
        raise typer.Exit(1)


@app.command()
def edit(
    entry_id: str = typer.Argument(..., help="Entry ID (8 hex chars)"),
    content: Optional[str] = typer.Option(None, "--content", "-c", help="Update content"),
    section: Optional[str] = typer.Option(None, "--section", "-s", help=f"Move to section: {', '.join(SECTIONS)}"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Replace tags (comma-separated)"),
):
    if not _validate_entry_id(entry_id):
        console.print(f"[red]Invalid entry ID format:[/red] {entry_id}")
        console.print("[dim]Expected: 8 hexadecimal characters (e.g., a1b2c3d4)[/dim]")
        raise typer.Exit(1)
    
    if content is None and section is None and tags is None:
        console.print("[red]Error:[/red] Provide at least one option: --content, --section, or --tags")
        raise typer.Exit(1)
    
    root = _root()
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    result = edit_entry(root, entry_id, content=content, section=section, tags=tag_list)
    if result:
        console.print(f"[green]✓ Updated[/green] {entry_id}")
        _print_table([result])
    else:
        console.print(f"[red]Not found:[/red] {entry_id}")
        raise typer.Exit(1)


@app.command()
def clear(
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm deletion"),
):
    root = _root()
    entries = read_entries(root)
    if not entries:
        console.print("[dim]No entries to clear.[/dim]")
        raise typer.Exit()
    
    console.print(f"[yellow]⚠ This will delete {len(entries)} entries:[/yellow]")
    _print_table(entries[:5])  
    if len(entries) > 5:
        console.print(f"[dim]... and {len(entries) - 5} more[/dim]")
    
    if not yes:
        console.print("\n[dim]Use --yes to confirm[/dim]")
        raise typer.Exit(1)
    
    try:
        count = clear_entries(root, confirm=True)
        console.print(f"[green]✓ Cleared {count} entries[/green]")
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
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
        console.print(f"[red]Folder not found:[/red] {folder}")
        raise typer.Exit(1)

    pattern = "**/*" if recursive else "*"
    supported = {".md", ".txt", ".pdf"}
    files = [f for f in folder.glob(pattern) if f.is_file() and f.suffix.lower() in supported]

    if not files:
        console.print(f"[yellow]No supported files found in {folder}[/yellow]")
        raise typer.Exit()

    console.print(f"\n[bold]Found {len(files)} files[/bold] in [dim]{folder}[/dim]\n")

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
        console.print(f"\n[green]Imported {imported} files[/green], skipped {skipped}")
    else:
        console.print(f"\n[dim]Dry run — nothing saved. Remove --dry-run to import.[/dim]")


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
            console.print(f"  [yellow]⚠[/yellow] Could not read {path.name}: {e}")
            return ""
    if path.suffix.lower() == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            return " ".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            console.print(f"[yellow]PDF support requires: pip install rememb[pdf][/yellow]")
            return ""
        except (OSError, PermissionError) as e:
            console.print(f"  [yellow]⚠[/yellow] Could not read PDF {path.name}: {e}")
            return ""
        except Exception as e:
            console.print(f"  [yellow]⚠[/yellow] Could not parse PDF {path.name}: {e}")
            return ""
    return ""



@app.command()
def rules(
    editor: Optional[str] = typer.Argument(None, help="Editor name (windsurf, cursor, claude, continue, vscode, all)"),
):
    _rules = _build_rules()

    editors = {
        "windsurf": ("Windsurf / Cascade", "windsurf_rules"),
        "cursor": ("Cursor", "cursor_rules"),
        "claude": ("Claude / Claude.md", "claude_rules"),
        "continue": ("Continue.dev", "continue_rules"),
        "vscode": ("VS Code + Copilot", "vscode_rules"),
    }

    if not editor:
        console.print("\n[bold]Available editors:[/bold]\n")
        for key, (label, _) in editors.items():
            console.print(f"  [cyan]rememb rules {key}[/cyan]  [dim]→ {label}[/dim]")
        console.print()
        return

    if editor.lower() == "all":
        for key, (label, rule_key) in editors.items():
            print(_rules[rule_key])
            print()
        return

    if editor.lower() not in editors:
        console.print(f"[red]Unknown editor:[/red] {editor}. Choose from: {', '.join(editors)}")
        raise typer.Exit(1)

    label, key = editors[editor.lower()]
    print(_rules[key])


@app.command()
def mcp():
    import asyncio
    try:
        from rememb.mcp_server import run_server as mcp_run_server
        asyncio.run(mcp_run_server())
    except ImportError as e:
        console.print(f"[red]MCP support requires:[/red] pip install rememb[mcp]")
        console.print(f"[dim]Details: {e}[/dim]")
        raise typer.Exit(1)


def _mcp_json_block() -> str:
    import shutil
    bin_path = shutil.which("rememb") or "rememb"
    return (
        "\n## MCP setup (recommended)\n"
        "Instead of CLI rules, add rememb as an MCP server so the agent calls it natively.\n\n"
        "```json\n"
        '{\n'
        '  "mcpServers": {\n'
        '    "rememb": {\n'
        f'      "command": "{bin_path}",\n'
        '      "args": ["mcp"]\n'
        '    }\n'
        '  }\n'
        '}\n'
        "```\n"
    )


def _build_rules() -> dict:
    base = (
        "# rememb\n\n"
        "You have access to `rememb`, a CLI tool for persistent memory across sessions.\n"
        "Use it to remember and retrieve context about this project and user.\n\n"
        "## Reading memory\n"
        "Run `rememb read --agent` to load all stored context before responding.\n"
        "Run `rememb search \"<topic>\" --agent` to find specific information.\n\n"
        "## Writing memory\n"
        "Run `rememb write \"<summary>\" --section <section>` when you learn something worth remembering.\n"
        "Available sections: project | actions | systems | requests | user | context\n\n"
        "## Rules\n"
        "- Always read memory at the start of a new session\n"
        "- Save important context after learning it — do not wait\n"
        "- Keep entries short (1-3 sentences)\n"
        "- Use --tags to categorize: `rememb write \"...\" --section project --tags tag1,tag2`\n"
        "\n## Editing memory\n"
        "Run `rememb edit <id> --content \"<new content>\"` to update an entry.\n"
        "Run `rememb edit <id> --section <section>` to move an entry to another section.\n"
        "Run `rememb delete <id> --yes` to remove an entry.\n"
        "Run `rememb clear --yes` to remove all entries (use with caution).\n"
        "\n## Importing files\n"
        "If the user asks to import notes or files into rememb:\n"
        "1. Run `rememb import <folder> --dry-run` to preview the files\n"
        "2. Read the content and decide which section fits each batch\n"
        "3. Run `rememb import <folder> --section <section>` to save\n"
        "4. For individual files with mixed content, use `rememb write` instead\n"
    )

    mcp_block = _mcp_json_block()

    windsurf = (
        base +
        "\n# Where to place (Windsurf / Cascade)\n"
        "- Settings → Cascade → Custom Instructions\n"
        "- Or: .windsurfrules at project root\n"
        + mcp_block +
        "Place the JSON above in: Settings → Cascade → MCP Servers\n"
    )

    cursor = (
        base +
        "\n# Where to place (Cursor)\n"
        "- .cursorrules at project root\n"
        "- Or: Settings → Rules for AI\n"
        + mcp_block +
        "Place the JSON above in: ~/.cursor/mcp.json\n"
    )

    claude = (
        base +
        "\n# Where to place (Claude Code)\n"
        "- CLAUDE.md at project root (auto-read every session)\n"
        + mcp_block +
        "Place the JSON above in: ~/.claude/mcp.json\n"
    )

    continue_dev = (
        base +
        "\n# Where to place (Continue.dev)\n"
        "- config.json → models[].systemMessage\n"
        "- Or: .continuerc.json → systemMessage\n"
    )

    vscode = (
        base +
        "\n# Where to place (VS Code + Copilot)\n"
        "- .github/copilot-instructions.md at project root (auto-read by Copilot)\n"
    )

    return {
        "windsurf_rules": windsurf,
        "cursor_rules": cursor,
        "claude_rules": claude,
        "continue_rules": continue_dev,
        "vscode_rules": vscode,
    }


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
