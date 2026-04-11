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

# Where to place (Cursor)
- .cursorrules at project root
- Or: Settings → Rules for AI

## Importing files
If the user asks to import notes or files into rememb:
1. Read each file content
2. Summarize and classify the section based on content (project/actions/systems/requests/user/context)
3. Run: `rememb write "<filename>: <summary>" --section <section> --tags <tag>`
Do NOT use `rememb import` for this — classify with your own judgment.
