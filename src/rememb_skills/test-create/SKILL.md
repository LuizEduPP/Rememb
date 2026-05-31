---
name: test-create
description: Generate test cases for code. Use when writing unit tests, integration tests, or verifying acceptance criteria.
---

# Create Tests

Generate comprehensive test cases for code.

## Overview

Use this skill to draft focused tests that cover behavior, edge cases, and failures without coupling the tests to implementation details.

## When to Use

- Writing new unit tests
- Adding integration or acceptance coverage
- Reproducing a bug with a failing test first
- Checking whether a change has enough verification

## Quick Start

1. Identify the behavior or acceptance criterion
2. Add one happy-path test
3. Add the most important edge case
4. Add the failure mode or invalid input case
5. Run the narrowest possible test command first

## Test Categories

| Category | Examples |
|----------|----------|
| ✅ Happy Path | Normal inputs, standard cases |
| 🔸 Edge Cases | Empty, boundary, min/max |
| ❌ Error Cases | Invalid inputs, failures |

## Python (pytest)

```python
import pytest

class TestFunction:
    def test_valid_input_returns_expected(self):
        assert function("valid") == "expected"
    
    def test_empty_input_returns_empty(self):
        assert function("") == ""
    
    def test_invalid_raises_error(self):
        with pytest.raises(ValueError):
            function(None)
```

## JavaScript (Jest)

```javascript
describe('function', () => {
  it('returns expected for valid input', () => {
    expect(fn('valid')).toBe('expected');
  });

  it('handles empty input', () => {
    expect(fn('')).toBe('');
  });

  it('throws for invalid', () => {
    expect(() => fn(null)).toThrow();
  });
});
```

## Naming Convention

```
test_[what]_[condition]_[expected]

test_login_valid_credentials_returns_token
test_login_wrong_password_raises_error
```

## Coverage Goals

| Type | Target |
|------|--------|
| Business logic | 80%+ |
| Utilities | 90%+ |
| UI | 60%+ |

## Best Practices
- Test behavior, not implementation
- One assertion per test
- Mock external dependencies
- Keep tests fast
## Core Workflow

Follow the primary workflow, commands, and decision points documented in the sections below.

## Examples

Use the examples and snippets already present in this document whenever they apply to the task.

## References

Use any linked scripts, assets, reference files, and companion resources mentioned in this document.

