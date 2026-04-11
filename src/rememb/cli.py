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
    global_root,
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
    """Returns memory root. Auto-initializes global ~/.rememb/ if nothing found."""
    root = find_root()
    if not is_initialized(root):
        root = global_root()
        init(root, project_name="global", global_mode=True)
    return root


@app.command()
def version():
    """Show rememb version."""
    console.print(f"rememb v{__version__}")


def init_cmd(
    path: Optional[Path] = typer.Argument(None, help="Project root (default: current dir)"),
    name: str = typer.Option("", "--name", "-n", help="Project name"),
):
    """Initialize .rememb/ in the current project (or globally with --global)."""
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


@app.command("import")
def import_cmd(
    folder: Path = typer.Argument(..., help="Folder to import files from"),
    section: str = typer.Option("context", "--section", "-s", help=f"Default section: {', '.join(SECTIONS)}"),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Search subfolders recursively"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without saving"),
):
    """Import .md, .txt, and .pdf files into memory."""
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

        # Truncate to 500 chars max per entry, strip surrogates
        summary = content.strip()[:500].replace("\n", " ").strip()
        summary = summary.encode("utf-8", errors="ignore").decode("utf-8")
        entry_section = section

        if dry_run:
            console.print(f"  [dim]{f.name}[/dim] → [cyan]{entry_section}[/cyan]  {summary[:80]}...")
        else:
            try:
                write_entry(root, entry_section, f"{f.stem}: {summary}", tags=[f.suffix.lstrip(".")])
                console.print(f"  [green]✓[/green] {f.name} → [{entry_section}]")
                imported += 1
            except Exception as e:
                console.print(f"  [red]✗[/red] {f.name}: {e}")
                skipped += 1

    if not dry_run:
        console.print(f"\n[green]Imported {imported} files[/green], skipped {skipped}")
    else:
        console.print(f"\n[dim]Dry run — nothing saved. Remove --dry-run to import.[/dim]")


def _read_file_content(path: Path) -> str:
    if path.suffix.lower() in {".md", ".txt"}:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""
    if path.suffix.lower() == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            return " ".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            console.print(f"[yellow]PDF support requires: pip install rememb[pdf][/yellow]")
            return ""
        except Exception:
            return ""
    return ""



@app.command()
def rules(
    editor: Optional[str] = typer.Argument(None, help="Editor: windsurf, cursor, claude, continue, vscode, all"),
):
    """Print ready-to-use agent rules/instructions for your editor."""
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
        "\n## Importing files\n"
        "If the user asks to import notes or files into rememb:\n"
        "1. Run `rememb import <folder> --dry-run` to preview the files\n"
        "2. Read the content and decide which section fits each batch\n"
        "3. Run `rememb import <folder> --section <section>` to save\n"
        "4. For individual files with mixed content, use `rememb write` instead\n"
    )

    windsurf = (
        base +
        "\n# Where to place (Windsurf / Cascade)\n"
        "- Settings → Cascade → Custom Instructions\n"
        "- Or: .windsurfrules at project root\n"
    )

    cursor = (
        base +
        "\n# Where to place (Cursor)\n"
        "- .cursorrules at project root\n"
        "- Or: Settings → Rules for AI\n"
    )

    claude = (
        base +
        "\n# Where to place (Claude Code)\n"
        "- CLAUDE.md at project root (auto-read every session)\n"
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
