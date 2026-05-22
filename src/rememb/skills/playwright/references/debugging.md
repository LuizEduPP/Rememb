# Debugging

## Debug Mode

```bash
# Full debug mode: headed, timeout=0, max-failures=1, workers=1
npx playwright test --debug

# Debug specific test
npx playwright test my-test.spec.ts --debug
```

### In-Test Pause

```typescript
test('debug this', async ({ page }) => {
  await page.goto('/');
  await page.pause(); // Opens Playwright Inspector, pauses here
  // Step through remaining actions in the Inspector
});
```

### Environment Variable Debug

```bash
PWDEBUG=1 npx playwright test    # Opens Inspector on every test
```

## Trace Viewer

Traces capture DOM snapshots, network, console, and actions.

### Configuration

```typescript
// playwright.config.ts
use: {
  trace: 'on-first-retry',  // Best balance: traces only on retries
  // Options: 'on', 'off', 'on-first-retry', 'retain-on-failure'
}
```

### View Traces

```bash
# From test report
npx playwright show-report
# Click on failed test → "Traces" tab

# From trace file directly
npx playwright show-trace test-results/my-test/trace.zip

# Remote trace
npx playwright show-trace <trace-zip-url>
```

### What Traces Contain

- Timeline of all actions
- DOM snapshots before/after each action
- Network requests and responses
- Console messages
- Test source code with highlighting
- Action log with timing

### Manual Trace API

```typescript
// Start/stop trace programmatically
await context.tracing.start({ screenshots: true, snapshots: true });
await page.goto('/');
await context.tracing.stop({ path: 'trace.zip' });
```

## UI Mode

Interactive test runner with watch mode:

```bash
npx playwright test --ui
```

Features:
- Run/debug individual tests
- Watch mode (re-runs on file change)
- Time-travel debugging with DOM snapshots
- Pick locators visually
- Filter by test status/text

## Headed Mode

```bash
# Run tests in visible browser
npx playwright test --headed

# Slow motion
npx playwright test --headed --slow-mo=500
```

## Console & Error Logging

```typescript
test('capture logs', async ({ page }) => {
  // Capture browser console
  page.on('console', msg => console.log(`BROWSER: ${msg.text()}`));

  // Capture page errors
  page.on('pageerror', err => console.log(`PAGE ERROR: ${err.message}`));

  await page.goto('/');
});
```

## Common Flaky Test Fixes

### 1. Race Conditions

```typescript
// ❌ BAD: evaluates once, no retry
expect(await page.locator('.item').count()).toBe(5);

// ✅ GOOD: auto-retries until true or timeout
await expect(page.locator('.item')).toHaveCount(5);
```

### 2. Network Timing

```typescript
// ❌ BAD: page may not have loaded data yet
await page.goto('/dashboard');
await expect(page.getByText('John')).toBeVisible();

// ✅ BETTER: wait for the API response
const responsePromise = page.waitForResponse('**/api/user');
await page.goto('/dashboard');
await responsePromise;
await expect(page.getByText('John')).toBeVisible();
```

### 3. Animations

```typescript
// Disable animations globally
// playwright.config.ts
use: {
  // Reduce motion for consistency
  reducedMotion: 'reduce',
}
```

### 4. Test Isolation

Each test gets a fresh `BrowserContext`. Never rely on state from previous tests.

```typescript
// ✅ Reset state explicitly if needed
test.beforeEach(async ({ request }) => {
  await request.post('/api/test/reset');
});
```

## Verbose Logging

```bash
# See all Playwright API calls
DEBUG=pw:api npx playwright test

# See browser protocol
DEBUG=pw:protocol npx playwright test
```

## VS Code Extension

Install "Playwright Test for VS Code":
- Run/debug tests from gutter icons
- Pick locators visually (record at cursor)
- Show browser during tests
- Live test results
