# rememb

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

# Where to place (Claude Code)
- CLAUDE.md at project root (auto-read every session)
