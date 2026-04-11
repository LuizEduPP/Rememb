# rememb

You have access to `rememb`, a CLI tool for persistent memory across sessions.
Use it to remember and retrieve context about this project and user.

## Reading memory
Run `rememb read --agent` to load all stored context before responding.
Run `rememb search "<topic>" --agent` to find specific information.

## Writing memory
Run `rememb write "<summary>" --section <section>` when you learn something worth remembering.
Available sections: project | actions | systems | requests | user | context

## Rules
- Always read memory at the start of a new session
- Save important context after learning it — do not wait
- Keep entries short (1-3 sentences)
- Use --tags to categorize: `rememb write "..." --section project --tags tag1,tag2`

# Where to place (VS Code + Copilot)
- .github/copilot-instructions.md at project root (auto-read by Copilot)
