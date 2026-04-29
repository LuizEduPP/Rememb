# Security Policy

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability in rememb, please report it responsibly.

### Reporting Process

1. **Email** your report to: **luizedupp@gmail.com**
   - Do **NOT** open a public GitHub issue for security vulnerabilities
   - Include "SECURITY:" in the subject line

2. **What to include:**
   - Vulnerability description (what is broken?)
   - Steps to reproduce (how to trigger it?)
   - Affected versions (which rememb versions are vulnerable?)
   - Suggested fix (if you have one)
   - Your contact info (for follow-up and credit)

3. **What we commit to:**
   - Acknowledge receipt within **24 hours**
   - Provide a fix timeline within **48 hours**
   - Keep you updated on progress
   - Credit you in the security advisory (unless you prefer anonymity)
   - Release a patched version within **7 days** for critical issues

### Severity Levels

| Level | Description | Example |
|-------|-------------|---------|
| **Critical** | Remote code execution, data breach, auth bypass | Memory injection, arbitrary file write |
| **High** | Privilege escalation, DoS, authentication flaw | Bypass semantic_scope checks |
| **Medium** | Information leak, input validation bypass | Exposed paths in error messages |
| **Low** | Hardening improvements, minor config issues | Weak default settings |

## Security Best Practices for Users

### Using rememb Safely

1. **File Permissions**
   - rememb stores sensitive memories in `~/.rememb/`
   - Ensure your home directory has restrictive permissions: `chmod 700 ~/.rememb`

2. **Semantic Security Guard**
   - The 88% similarity threshold prevents most duplicates
   - Review entries before storing highly sensitive information
   - rememb does NOT encrypt data at rest (local file system only)

3. **Updates**
   - Keep rememb updated: `pip install --upgrade rememb`
   - Subscribe to [releases](https://github.com/LuizEduPP/Rememb/releases) for security patches

4. **Dependency Audit**
   - rememb depends on `sentence-transformers`, `textual`, `typer`, `mcp`
   - These are vetted production libraries
   - We monitor for vulnerability alerts via GitHub Dependabot

## Vulnerability Disclosure Timeline

Once a vulnerability is reported:

| Timeline | Action |
|----------|--------|
| Day 0 | Acknowledge receipt, assign severity |
| Day 1-2 | Develop and test fix |
| Day 3-7 | Release patched version (critical issues: Day 1-2) |
| Day 7+ | Publish security advisory with credit |

## Supported Versions

- **v0.4.x** (current) — **Active** (security patches + features)
- **v0.3.x** — **Limited Support** (security patches only)
- **v0.2.x and older** — **Unsupported** (end-of-life)

## Security Headers & Compliance

rememb is a **local-first tool** with no network dependencies. There are no:
- ❌ Remote APIs to attack
- ❌ Cloud storage to compromise
- ❌ Authentication servers to bypass
- ✅ Only local JSON-backed storage with file system permissions

## References

- [OWASP Secure Coding Practices](https://owasp.org/www-project-secure-coding-practices-quick-reference-guide/)
- [Python Security Best Practices](https://python.readthedocs.io/en/latest/library/security_warnings.html)
- [CVE Database](https://cve.mitre.org/)

---

**Last Updated:** April 28, 2026
**Contact:** luizedupp@gmail.com
