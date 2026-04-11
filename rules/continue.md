# rememb — Agent Memory Rules (Continue.dev)

At the START of every conversation:
1. Run: `rememb read --agent` and absorb the memory context
2. If searching for specific context: `rememb search "<topic>" --agent`

At the END of every conversation (or when significant context is established):
1. Run: `rememb write "<summary>" --section <section>`
   Sections: project | actions | systems | requests | user | context

Rules:
- Always read memory before acting on a new session
- Always write memory after learning something important about the project or user
- Keep entries concise (1-3 sentences max per entry)
- Tag entries when relevant: `--tags tag1,tag2`

# Continue.dev specific:
- Paste into: .continuerc.json → systemMessage field
- Or into: config.json → models[].systemMessage
