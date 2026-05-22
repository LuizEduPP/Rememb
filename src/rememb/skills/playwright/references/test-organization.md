# Test Organization

## Fixtures

Fixtures provide isolated, on-demand setup/teardown for each test.

```typescript
// e2e/fixtures.ts
import { test as base, Page } from '@playwright/test';

type MyFixtures = {
  todoPage: TodoPage;
  authenticatedPage: Page;
};

export const test = base.extend<MyFixtures>({
  // Simple fixture
  todoPage: async ({ page }, use) => {
    const todoPage = new TodoPage(page);
    await todoPage.goto();
    await use(todoPage);
    // Teardown runs after test
  },

  // Fixture with setup + teardown
  authenticatedPage: async ({ page }, use) => {
    await page.goto('/login');
    await page.getByLabel('Email').fill('user@test.com');
    await page.getByLabel('Password').fill('password');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await page.waitForURL(/dashboard/);
    await use(page);
    // Teardown: automatic context cleanup
  },
});

export { expect } from '@playwright/test';
```

### Fixture Scopes

```typescript
// Worker-scoped fixture (shared across tests in same worker)
export const test = base.extend<{}, { dbConnection: DBConnection }>({
  dbConnection: [async ({}, use) => {
    const db = await connectDB();
    await use(db);
    await db.close();
  }, { scope: 'worker' }],
});
```

### Gotchas

- **Array values**: Must wrap in extra array: `persons: [actualArray, { scope: 'test' }]`
- **`box: 'self'`**: Hides only fixture step in report but shows inner steps
- **Fixture teardowns + `afterEach`**: Get a SEPARATE timeout from the test itself
- Fixtures are lazy — only instantiated when a test actually uses them

## Annotations

```typescript
test.skip('not ready yet', async ({ page }) => { /* skipped */ });

test('fails on webkit', async ({ page, browserName }) => {
  test.skip(browserName === 'webkit', 'Not supported on WebKit');
});

test.fixme('broken test', async ({ page }) => { /* not run, marked TODO */ });

test('known failure', async ({ page }) => {
  test.fail(); // Playwright COMPLAINS if this test passes
});

test('heavy test', async ({ page }) => {
  test.slow(); // Triples the timeout
});

// Tags for filtering
test('critical flow @smoke @critical', async ({ page }) => { });
// Run with: npx playwright test --grep @smoke
```

### `test.fail()` Behavior

Marks test as "expected to fail". If the test PASSES, Playwright reports an error. Use this for known bugs with tracked issues.

## Parallel Execution

```typescript
// playwright.config.ts
export default defineConfig({
  fullyParallel: true,    // Parallelize within files
  workers: process.env.CI ? 1 : undefined, // Default: 50% of CPU cores
});

// Per-file opt-out of parallel
test.describe.configure({ mode: 'serial' });
```

### Key Behaviors

- Each worker gets its own browser instance
- Tests in different files run in parallel by default
- `fullyParallel: true` also parallelizes tests WITHIN a file
- **Worker killed after any failure** — remaining tests in that worker are skipped
- Default workers = 50% of CPU cores

## Serial Mode

```typescript
test.describe.configure({ mode: 'serial' });

test('step 1', async ({ page }) => { /* ... */ });
test('step 2', async ({ page }) => { /* depends on step 1 */ });
```

**Gotcha**: On retry, ALL tests in the serial group re-run, not just the failed one.

## Retries

```typescript
// playwright.config.ts
export default defineConfig({
  retries: process.env.CI ? 2 : 0,
});
```

- Retried tests get a fresh worker, browser context, and page
- `trace: 'on-first-retry'` captures traces only on retry (good balance)

## Sharding

```bash
# Split across 4 machines
npx playwright test --shard=1/4
npx playwright test --shard=2/4
```

- With `fullyParallel: true`: balances at TEST level
- Without: balances at FILE level

### Merging Shard Reports

```bash
npx playwright merge-reports ./all-blob-reports --reporter html
```

## Timeouts

### Hierarchy

| Timeout | Default | Config |
|---------|---------|--------|
| Test timeout | 30s | `timeout` |
| Expect/assertion | 5s | `expect.timeout` |
| Action (click, fill) | 0 (no timeout) | `actionTimeout` |
| Navigation (goto) | 0 (no timeout) | `navigationTimeout` |

**Gotcha**: Action and navigation timeouts default to 0 (infinite), NOT 30 seconds.

```typescript
// Per-test timeout
test('slow test', async ({ page }) => {
  test.setTimeout(60_000);
});

// Fixture teardown has its own timeout
// afterEach + fixture teardowns share a separate timeout equal to test timeout
```

### `expect.toPass` Timeout

```typescript
// ❌ Does NOT inherit expect timeout — defaults to 0 (single attempt)
await expect(async () => {
  const response = await page.request.get('/api/status');
  expect(response.status()).toBe(200);
}).toPass();

// ✅ Explicit timeout
await expect(async () => {
  const response = await page.request.get('/api/status');
  expect(response.status()).toBe(200);
}).toPass({ timeout: 10_000 });
```

## Test Describe & Hooks

```typescript
test.describe('Feature', () => {
  test.beforeAll(async () => { /* once before all tests */ });
  test.beforeEach(async ({ page }) => { /* before each test */ });
  test.afterEach(async ({ page }) => { /* after each test */ });
  test.afterAll(async () => { /* once after all tests */ });

  test('test 1', async ({ page }) => { });
});
```

## Parameterized Tests

```typescript
const users = [
  { role: 'admin', expected: '/admin' },
  { role: 'user', expected: '/dashboard' },
];

for (const { role, expected } of users) {
  test(`${role} redirects to ${expected}`, async ({ page }) => {
    await page.goto(`/login?role=${role}`);
    await expect(page).toHaveURL(expected);
  });
}
```

## Project Dependencies

```typescript
// playwright.config.ts
projects: [
  { name: 'setup', testMatch: /.*\.setup\.ts/ },
  {
    name: 'chromium',
    use: { ...devices['Desktop Chrome'] },
    dependencies: ['setup'],
  },
],
```

Use project dependencies instead of `globalSetup` — they integrate with traces, fixtures, and HTML report.
