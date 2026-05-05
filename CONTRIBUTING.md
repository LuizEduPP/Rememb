# Contributing to rememb

Thank you for your interest in contributing to rememb!

## Development Setup

1. Clone the repository:
```bash
git clone https://github.com/LuizEduPP/rememb.git
cd rememb
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

- Use Python 3.9+ type hints (`list[str]` instead of `List[str]`)
- Follow PEP 8 guidelines
- Use snake_case for function and variable names
- Add docstrings to all public functions
- Keep functions focused and under 50 lines when possible

## Project Structure

```
src/rememb/
├── __init__.py          # Version
├── cli.py               # CLI entrypoints and help output
├── config.py            # Default config and constants
├── exceptions.py        # Custom exceptions
├── helpers.py           # Persistence, validation and search helpers
├── mcp_server.py        # MCP server surface
├── store.py             # Core memory API
├── tui.py               # Textual UI
└── utils.py             # Shared utilities
```

## Making Changes

1. Create a branch for your feature:
```bash
git checkout -b feature/your-feature-name
```

2. Make your changes and test locally

3. Run compilation check:
```bash
python -m py_compile src/rememb/*.py
```

## Submitting Changes

1. Push your branch:
```bash
git push origin feature/your-feature-name
```

2. Open a Pull Request on GitHub

3. Describe your changes in the PR description

Release automation and Trusted Publishing are documented in RELEASE.md.

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
- Additional file format support (e.g., .docx, .rst)
- Enhanced semantic search options
- CLI UX improvements

## Questions?

Open an issue on GitHub for questions or discussion.
