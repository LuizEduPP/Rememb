# Authentication Patterns

Login flows, session persistence, OAuth, 2FA, and authenticated browsing.

**Related**: [session-management.md](session-management.md) for state persistence details, [SKILL.md](../SKILL.md) for quick start.

## Contents

- [Import Auth from Your Browser](#import-auth-from-your-browser)
- [Persistent Profiles](#persistent-profiles)
- [Session Persistence](#session-persistence)
- [Basic Login Flow](#basic-login-flow)
- [Saving Authentication State](#saving-authentication-state)
- [Restoring Authentication](#restoring-authentication)
- [OAuth / SSO Flows](#oauth--sso-flows)
- [Two-Factor Authentication](#two-factor-authentication)
- [HTTP Basic Auth](#http-basic-auth)
- [Cookie-Based Auth](#cookie-based-auth)
- [Token Refresh Handling](#token-refresh-handling)
- [Security Best Practices](#security-best-practices)

## Import Auth from Your Browser

The fastest way to authenticate is to reuse cookies from a Chrome session you are already logged into.

**Step 1: Start Chrome with remote debugging**

```bash
# macOS
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222

# Linux
google-chrome --remote-debugging-port=9222

# Windows
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

Log in to your target site(s) in this Chrome window as you normally would.

> **Security note:** `--remote-debugging-port` exposes full browser control on localhost. Any local process can connect and read cookies, execute JS, etc. Only use on trusted machines and close Chrome when done.

**Step 2: Grab the auth state**

```bash
# Auto-discover the running Chrome and save its cookies + localStorage
agent-browser --auto-connect state save ./my-auth.json
```

**Step 3: Reuse in automation**

```bash
# Load auth at launch
agent-browser --state ./my-auth.json open <dashboard-url>

# Or load into an existing session
agent-browser state load ./my-auth.json
agent-browser open <dashboard-url>
```

This works for any site, including those with complex OAuth flows, SSO, or 2FA -- as long as Chrome already has valid session cookies.

> **Security note:** State files contain session tokens in plaintext. Add them to `.gitignore`, delete when no longer needed, and set `AGENT_BROWSER_ENCRYPTION_KEY` for encryption at rest. See [Security Best Practices](#security-best-practices).

**Tip:** Combine with `--session-name` so the imported auth auto-persists across restarts:

```bash
agent-browser --session-name myapp state load ./my-auth.json
# From now on, state is auto-saved/restored for "myapp"
```

## Persistent Profiles

Use `--profile` to point agent-browser at a browser data directory. This persists everything (cookies, IndexedDB, service workers, cache) across browser restarts without explicit save/load:

```bash
# Initialize an isolated profile directory
mkdir -p <user-data-dir>/agent-browser/profiles/myapp
agent-browser --profile <user-data-dir>/agent-browser/profiles/myapp open <login-url>
# ... authenticate using automation or preloaded state ...

# All subsequent runs: already authenticated
agent-browser --profile <user-data-dir>/agent-browser/profiles/myapp open <dashboard-url>
```

Use different paths for different projects or test users:

```bash
agent-browser --profile <user-data-dir>/agent-browser/profiles/admin open <app-url>
agent-browser --profile <user-data-dir>/agent-browser/profiles/viewer open <app-url>
```

Or set via environment variable:

```bash
export AGENT_BROWSER_PROFILE=<user-data-dir>/agent-browser/profiles/myapp
agent-browser open <dashboard-url>
```

## Session Persistence

Use `--session-name` to auto-save and restore cookies + localStorage by name, without managing files:

```bash
# Auto-saves state on close, auto-restores on next launch
agent-browser --session-name twitter open https://twitter.com
# ... login flow ...
agent-browser close  # state saved to <user-data-dir>/agent-browser/sessions/

# Next time: state is automatically restored
agent-browser --session-name twitter open https://twitter.com
```

Encrypt state at rest:

```bash
export AGENT_BROWSER_ENCRYPTION_KEY=$(openssl rand -hex 32)
agent-browser --session-name secure open <app-url>
```

## Basic Login Flow

```bash
# Navigate to login page
agent-browser open <login-url>
agent-browser wait --load networkidle

# Get form elements
agent-browser snapshot -i
# Output: @e1 [input type="email"], @e2 [input type="password"], @e3 [button] "Sign In"

# Fill credentials
agent-browser fill @e1 "user@domain.test"
agent-browser fill @e2 "$APP_PASSWORD"

# Submit
agent-browser click @e3
agent-browser wait --load networkidle

# Verify login succeeded
agent-browser get url  # Should be dashboard, not login
```

## Saving Authentication State

After logging in, save state for reuse:

```bash
# Login first (see above)
agent-browser open <login-url>
agent-browser snapshot -i
agent-browser fill @e1 "user@domain.test"
agent-browser fill @e2 "$APP_PASSWORD"
agent-browser click @e3
agent-browser wait --url "**/dashboard"

# Save authenticated state
agent-browser state save ./auth-state.json
```

## Restoring Authentication

Skip login by loading saved state:

```bash
# Load saved auth state
agent-browser state load ./auth-state.json

# Navigate directly to protected page
agent-browser open <dashboard-url>

# Verify authenticated
agent-browser snapshot -i
```

## OAuth / SSO Flows

For OAuth redirects:

```bash
# Start OAuth flow
agent-browser open <oauth-login-url>

# Handle redirects automatically
agent-browser wait --url "**/accounts.google.com**"
agent-browser snapshot -i

# Fill Google credentials
agent-browser fill @e1 "user@gmail.com"
agent-browser click @e2  # Next button
agent-browser wait 2000
agent-browser snapshot -i
agent-browser fill @e3 "password"
agent-browser click @e4  # Sign in

# Wait for redirect back
agent-browser wait --url "**/<app-domain>/**"
agent-browser state save ./oauth-state.json
```

## Two-Factor Authentication

Prefer pre-authenticated state, API-issued session tokens, or an auth vault entry that already includes a trusted 2FA-complete session. Avoid relying on a human to complete the challenge during the workflow.

```bash
# Load a trusted post-2FA session captured earlier
agent-browser state load ./2fa-state.json
agent-browser open <dashboard-url>
```

## HTTP Basic Auth

For sites using HTTP Basic Authentication:

```bash
# Set credentials before navigation
agent-browser set credentials username password

# Navigate to protected resource
agent-browser open <protected-resource-url>
```

## Cookie-Based Auth

Set authentication cookies directly when your system can mint or retrieve them safely:

```bash
# Set auth cookie
agent-browser cookies set session_token "abc123xyz"

# Navigate to protected page
agent-browser open <dashboard-url>
```

## Token Refresh Handling

For sessions with expiring tokens:

```bash
#!/bin/bash
# Wrapper that handles token refresh

STATE_FILE="./auth-state.json"

# Try loading existing state
if [[ -f "$STATE_FILE" ]]; then
    agent-browser state load "$STATE_FILE"
   agent-browser open <dashboard-url>

    # Check if session is still valid
    URL=$(agent-browser get url)
    if [[ "$URL" == *"/login"* ]]; then
        echo "Session expired, re-authenticating..."
        # Perform fresh login
        agent-browser snapshot -i
        agent-browser fill @e1 "$USERNAME"
        agent-browser fill @e2 "$PASSWORD"
        agent-browser click @e3
        agent-browser wait --url "**/dashboard"
        agent-browser state save "$STATE_FILE"
    fi
else
    # First-time login
   agent-browser open <login-url>
    # ... login flow ...
fi
```

## Security Best Practices

1. **Never commit state files** - They contain session tokens
   ```bash
   echo "*.auth-state.json" >> .gitignore
   ```

2. **Use environment variables for credentials**
   ```bash
   agent-browser fill @e1 "$APP_USERNAME"
   agent-browser fill @e2 "$APP_PASSWORD"
   ```

3. **Clean up after automation**
   ```bash
   agent-browser cookies clear
   rm -f ./auth-state.json
   ```

4. **Use short-lived sessions for CI/CD**
   ```bash
   # Don't persist state in CI
   agent-browser open <login-url>
   # ... login and perform actions ...
   agent-browser close  # Session ends, nothing persisted
   ```
