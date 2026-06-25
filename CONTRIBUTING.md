# Contributing to rememb

Thank you for your interest in contributing to rememb!

## Development Setup

1. Clone the repository:

```bash
git clone https://github.com/LuizEduPP/Rememb.git
cd Rememb
```

2. Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install in development mode:

```bash
pip install -e ".[dev]"
```

## Code Style

- Use Python 3.10+ type hints (`list[str]` instead of `List[str]`)
- Follow PEP 8 guidelines
- Use snake_case for function and variable names
- Add docstrings to all public functions
- Keep functions focused and under 50 lines when possible

## Project Structure

```
src/rememb/
├── __init__.py          # Version
├── cli.py               # CLI entrypoints (web UI default, mcp subcommand)
├── config.py            # Default config and constants
├── exceptions.py        # Custom exceptions
├── helpers.py           # Store context, keyword search, legacy semantic helpers
├── mcp_server.py        # MCP server (17 public tools)
├── utils.py             # Shared utilities and skill discovery
├── store/
│   ├── __init__.py      # Public store API
│   ├── crud.py          # CRUD, search, consolidate
│   └── agent_tools.py   # Agent-facing store helpers
├── storage/
│   ├── __init__.py      # JSON / SQLite backend resolution
│   ├── base.py
│   ├── json_backend.py
│   ├── sqlite_backend.py
│   └── locking.py
└── web/
    ├── app.py           # FastAPI app
    ├── deps.py          # Store dependency (~/.rememb)
    ├── schemas.py
    ├── routes/
    │   ├── entries.py
    │   └── system.py
    └── static/          # SPA (index.html, app.js, style.css)

src/rememb_skills/       # 60 bundled agent skills (SKILL.md per skill)
tests/                   # pytest suite
```

## Making Changes

1. Create a branch for your feature:

```bash
git checkout -b feature/your-feature-name
```

2. Make your changes and test locally:

```bash
python -m pytest
```

3. Run compilation check:

```bash
python -m py_compile src/rememb/*.py
python -m py_compile src/rememb/store/*.py
python -m py_compile src/rememb/storage/*.py
```

## Submitting Changes

1. Push your branch:

```bash
git push origin feature/your-feature-name
```

2. Open a Pull Request on GitHub

3. Describe your changes in the PR description

Release automation and Trusted Publishing are documented in [RELEASE.md](RELEASE.md).

## Guidelines

- **Keep it simple**: rememb is designed to stay local-first and lightweight to operate
- **Local-first**: Prefer local storage over remote services
- **Fail-fast**: Explicit errors over silent fallbacks
- **Type safety**: Use type hints for all public APIs
- **Documentation**: Update CHANGELOG.md for user-facing changes

## Areas for Contribution

- Bug fixes
- Documentation improvements
- Performance optimizations
- CLI and Web UI UX improvements
- MCP tool and test coverage
- Bundled skill maintenance

## Questions?

Open an issue on GitHub for questions or discussion.
