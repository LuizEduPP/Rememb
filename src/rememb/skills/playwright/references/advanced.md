# Advanced

## Page Object Model (POM)

### Base Page

```typescript
// e2e/pages/base.page.ts
import { Page, Locator } from '@playwright/test';

export abstract class BasePage {
  constructor(protected page: Page) {}

  async navigate(path: string) {
    await this.page.goto(path);
  }

  get header() { return this.page.getByRole('banner'); }
  get footer() { return this.page.getByRole('contentinfo'); }
}
```

### Page Implementation

```typescript
// e2e/pages/login.page.ts
import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './base.page';

export class LoginPage extends BasePage {
  readonly emailInput: Locator;
  readonly passwordInput: Locator;
  readonly submitButton: Locator;
  readonly errorMessage: Locator;

  constructor(page: Page) {
    super(page);
    this.emailInput = page.getByLabel('Email');
    this.passwordInput = page.getByLabel('Password');
    this.submitButton = page.getByRole('button', { name: 'Sign in' });
    this.errorMessage = page.getByRole('alert');
  }

  async goto() { await this.navigate('/login'); }

  async login(email: string, password: string) {
    await this.emailInput.fill(email);
    await this.passwordInput.fill(password);
    await this.submitButton.click();
  }

  async expectError(msg: string) {
    await expect(this.errorMessage).toContainText(msg);
  }
}
```

### POM as Fixtures

```typescript
// e2e/fixtures.ts
import { test as base } from '@playwright/test';
import { LoginPage } from './pages/login.page';

export const test = base.extend<{ loginPage: LoginPage }>({
  loginPage: async ({ page }, use) => {
    await use(new LoginPage(page));
  },
});
export { expect } from '@playwright/test';
```

### Best Practices

- Keep assertions OUT of page objects — put them in tests or as `expect*` helper methods
- Use fixtures to inject page objects (cleaner than `new LoginPage(page)` in every test)
- Locators as properties — lazy evaluation, defined once
- Component page objects for reusable sections (nav, sidebar, modals)

## Clock Mocking

### Fixed Time

```typescript
test('shows correct date', async ({ page }) => {
  // Freeze Date.now() but timers still run
  await page.clock.setFixedTime(new Date('2024-01-15T10:00:00Z'));
  await page.goto('/');
  await expect(page.getByText('January 15, 2024')).toBeVisible();
});
```

### Full Clock Control

```typescript
test('timer behavior', async ({ page }) => {
  // MUST call install() BEFORE any clock-related calls
  await page.clock.install({ time: new Date('2024-01-15T10:00:00Z') });
  await page.goto('/');

  // Fast-forward time
  await page.clock.fastForward('01:30:00'); // 1 hour 30 minutes
  await page.clock.fastForward(5000);       // 5 seconds in ms

  // Advance to specific time
  await page.clock.setFixedTime(new Date('2024-01-15T12:00:00Z'));
});
```

**Gotcha**: `clock.install()` MUST be called BEFORE any other clock calls. Behavior is undefined otherwise.

**Difference**: `setFixedTime` freezes `Date.now()` but lets timers run. `install` + `fastForward` gives full control over both.

## Evaluating JavaScript

### Basic Evaluation

```typescript
// Run JS in browser context
const title = await page.evaluate(() => document.title);

// Pass arguments (SINGLE optional argument only)
const text = await page.evaluate(
  selector => document.querySelector(selector)?.textContent,
  '#my-element'
);

// Pass multiple values via object
const result = await page.evaluate(
  ({ x, y }) => x + y,
  { x: 1, y: 2 }
);
```

**Gotcha**: Arrow function returning object literal needs parentheses:
```typescript
// ✅ Correct
await page.evaluate(() => ({ foo: 'bar' }));

// ❌ Wrong — parsed as block statement
await page.evaluate(() => { foo: 'bar' });
```

### Evaluate Handle (Return DOM reference)

```typescript
const handle = await page.evaluateHandle(() => document.body);
// Use handle in subsequent evaluations
await page.evaluate(body => body.innerHTML, handle);
await handle.dispose(); // Clean up
```

## Component Testing (Experimental)

Test individual components without full app:

```typescript
// playwright-ct.config.ts
import { defineConfig } from '@playwright/experimental-ct-react';

export default defineConfig({
  testDir: './src',
  use: {
    ctPort: 3100,
  },
});
```

```typescript
import { test, expect } from '@playwright/experimental-ct-react';
import { Button } from './Button';

test('button click', async ({ mount }) => {
  let clicked = false;
  const component = await mount(
    <Button onClick={() => { clicked = true; }}>Click me</Button>
  );
  await component.click();
  expect(clicked).toBeTruthy();
});
```

### Gotchas

- **Experimental** — API may change
- Cannot pass complex Node.js objects to components
- Callbacks are async across the boundary
- Vite config is NOT reused — component testing has its own config
- Must use `playwright-ct.config.ts` (separate from main config)

## Accessibility Testing

### With @axe-core/playwright

```typescript
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('page has no a11y violations', async ({ page }) => {
  await page.goto('/');

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

// Scan specific section
const results = await new AxeBuilder({ page })
  .include('#main-content')
  .exclude('#third-party-widget')
  .analyze();

// Disable specific rules
const results = await new AxeBuilder({ page })
  .disableRules(['color-contrast'])
  .analyze();
```

### ARIA Snapshot Testing

```typescript
await expect(page.getByRole('navigation')).toMatchAriaSnapshot(`
  - navigation "Main":
    - link "Home"
    - link "About"
    - link "Contact"
`);
```

## Dialogs

```typescript
// MUST register handler BEFORE the action that triggers the dialog
page.on('dialog', async dialog => {
  console.log(dialog.message());
  await dialog.accept(); // or dialog.dismiss()
});

await page.getByRole('button', { name: 'Delete' }).click();

// One-time dialog handler
page.once('dialog', dialog => dialog.accept('typed text'));
```

**Gotcha**: If you don't handle the dialog (accept/dismiss), the triggering action will hang forever.

## Frames

```typescript
// By name or URL
const frame = page.frame({ name: 'my-frame' });
const frame = page.frame({ url: /api\.example\.com/ });

// FrameLocator (preferred — auto-waits)
const stripe = page.frameLocator('iframe[name="stripe"]');
await stripe.getByPlaceholder('Card number').fill('4242424242424242');
```

## Browser Contexts

Each test gets an isolated `BrowserContext` (like an incognito profile):

```typescript
// Create additional contexts in a test
const context = await browser.newContext();
const page = await context.newPage();

// Contexts are isolated: separate cookies, localStorage, etc.
```

## Touch Events

```typescript
// Tap
await page.getByRole('button').tap();

// Enable touch in config
use: {
  hasTouch: true,
}
```

**Gotcha**: `dispatchEvent` does NOT set `Event.isTrusted = true`. Use Playwright's built-in actions for trusted events.

## Codegen (Test Generator)

```bash
# Opens browser, records actions as test code
npx playwright codegen http://localhost:3000

# With specific viewport
npx playwright codegen --viewport-size=1280,720 http://localhost:3000

# With device emulation
npx playwright codegen --device="iPhone 13" http://localhost:3000
```
