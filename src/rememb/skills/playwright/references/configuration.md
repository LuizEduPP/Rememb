# Configuration

## Full Config Example

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined, // Default: 50% of CPU cores
  reporter: [
    ['html'],
    ['list'],
    process.env.CI ? ['github'] : ['line'],
  ],

  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    testIdAttribute: 'data-testid', // Customize test ID attribute
  },

  projects: [
    // Auth setup project
    { name: 'setup', testMatch: /.*\.setup\.ts/ },

    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['setup'],
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
      dependencies: ['setup'],
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
      dependencies: ['setup'],
    },
    // Mobile
    {
      name: 'mobile-chrome',
      use: { ...devices['Pixel 5'] },
      dependencies: ['setup'],
    },
    {
      name: 'mobile-safari',
      use: { ...devices['iPhone 12'] },
      dependencies: ['setup'],
    },
  ],

  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
```

## Web Server

```typescript
webServer: {
  command: 'npm run dev',
  url: 'http://localhost:3000',           // Readiness check: accepts 2xx, 3xx, 400-403
  reuseExistingServer: !process.env.CI,   // Reuse in dev, start fresh in CI
  timeout: 120_000,                        // Startup timeout
  env: { DATABASE_URL: 'test-db' },
  stdout: 'pipe',                          // Pipe stdout to test output
},

// Multiple servers
webServer: [
  { command: 'npm run api', port: 4000 },
  { command: 'npm run app', port: 3000 },
],
```

**Gotcha**: `url` readiness check accepts status codes 2xx, 3xx, and 400-403. A 404 means "server is ready". Use `port` instead if you need strict health checking.

**Gotcha**: `gracefulShutdown` option is ignored on Windows.

## Projects

Projects run tests against different configurations:

```typescript
projects: [
  // Different browsers
  { name: 'chromium', use: { ...devices['Desktop Chrome'] } },

  // Different auth states
  {
    name: 'logged-in',
    use: { storageState: '.auth/user.json' },
    dependencies: ['setup'],
  },
  {
    name: 'logged-out',
    use: { storageState: { cookies: [], origins: [] } },
  },

  // Different base URLs
  { name: 'staging', use: { baseURL: '<staging-url>' } },
],
```

### Dependencies vs globalSetup

Prefer project dependencies over `globalSetup`:

| Feature | Project Dependencies | globalSetup |
|---------|---------------------|-------------|
| Trace support | ✅ | ❌ |
| Fixtures | ✅ | ❌ |
| HTML report | ✅ | ❌ |
| Parallelizable | ✅ | ❌ |

## Reporters

```typescript
reporter: [
  ['html'],                                    // Interactive HTML report
  ['list'],                                    // Console list output
  ['json', { outputFile: 'results.json' }],   // JSON output
  ['junit', { outputFile: 'results.xml' }],   // JUnit XML
  ['github'],                                  // GitHub Actions annotations
  ['blob'],                                    // For merging shard reports
],
```

### Custom Reporter

```typescript
// custom-reporter.ts
import type { Reporter, TestCase, TestResult } from '@playwright/test/reporter';

class MyReporter implements Reporter {
  onTestEnd(test: TestCase, result: TestResult) {
    console.log(`${test.title}: ${result.status}`);
  }
}
export default MyReporter;

// playwright.config.ts
reporter: [['./custom-reporter.ts']],
```

## Emulation

```typescript
use: {
  // Viewport
  viewport: { width: 1280, height: 720 },

  // Geolocation
  geolocation: { latitude: 48.858455, longitude: 2.294474 },
  permissions: ['geolocation'],

  // Locale & timezone (browser only, NOT test runner)
  locale: 'fr-FR',
  timezoneId: 'Europe/Paris',

  // Color scheme
  colorScheme: 'dark',

  // Reduced motion
  reducedMotion: 'reduce',

  // User agent
  userAgent: 'Custom UA',
},
```

**Gotcha**: Device spread order matters. Overrides AFTER the spread:

```typescript
// ✅ CORRECT: override viewport after device spread
use: { ...devices['Desktop Chrome'], viewport: { width: 1920, height: 1080 } }

// ❌ WRONG: device spread overwrites custom viewport
use: { viewport: { width: 1920, height: 1080 }, ...devices['Desktop Chrome'] }
```

## TypeScript

Playwright transpiles TypeScript but does NOT type-check. Only these tsconfig options are supported:
- `allowJs`
- `baseUrl`
- `paths`
- `references`

Run `tsc --noEmit` separately for type checking.

## CI/CD (GitHub Actions)

```yaml
name: E2E Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: 'npm'
      - run: npm ci
      - run: npx playwright install --with-deps chromium
      - run: npx playwright test --project=chromium
        env:
          BASE_URL: ${{ secrets.STAGING_URL }}
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: playwright-report/
          retention-days: 7
```

### Docker

```bash
# Use official Playwright Docker image
docker run --rm -v $(pwd):/work -w /work mcr.microsoft.com/playwright:v1.50.0-noble \
  npx playwright test
```

## Environment Variables

```typescript
// Access in config
use: {
  baseURL: process.env.BASE_URL || 'http://localhost:3000',
},

// Access in tests
test('env test', async () => {
  const apiKey = process.env.API_KEY;
});
```

Use `.env` file with `dotenv` or pass via CLI:
```bash
BASE_URL=<staging-url> npx playwright test
```

## Global Setup/Teardown

Prefer project dependencies. If you must use globalSetup:

```typescript
// global-setup.ts
import { chromium, FullConfig } from '@playwright/test';

async function globalSetup(config: FullConfig) {
  // No fixtures, no traces, no HTML report integration
  const browser = await chromium.launch();
  const page = await browser.newPage();
  // ... setup logic
  await browser.close();
}
export default globalSetup;

// playwright.config.ts
export default defineConfig({
  globalSetup: require.resolve('./global-setup'),
  globalTeardown: require.resolve('./global-teardown'),
});
```

**Gotcha**: `test.use({ baseURL: undefined })` resets to the config value, NOT to truly undefined.
