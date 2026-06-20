# Authentication

## Setup Project for Auth

Best approach: Use a setup project that runs once and saves auth state.

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  projects: [
    { name: 'setup', testMatch: /.*\.setup\.ts/ },
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        storageState: '.auth/user.json',
      },
      dependencies: ['setup'],
    },
  ],
});
```

## Auth Setup File

```typescript
// e2e/auth.setup.ts
import { test as setup, expect } from '@playwright/test';
import path from 'path';

const authFile = path.join(__dirname, '../.auth/user.json');

setup('authenticate', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Email').fill(process.env.TEST_USER_EMAIL!);
  await page.getByLabel('Password').fill(process.env.TEST_USER_PASSWORD!);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/dashboard/);

  // Save auth state
  await page.context().storageState({ path: authFile });
});
```

Add `.auth/` to `.gitignore`.

## What `storageState` Covers

- Cookies
- localStorage
- IndexedDB

**Does NOT cover**: sessionStorage. If your app uses sessionStorage for auth tokens, use a different approach (e.g., API-based login or inject storage in `beforeEach`).

## Multi-Role Authentication

```typescript
// playwright.config.ts
projects: [
  { name: 'setup', testMatch: /.*\.setup\.ts/ },
  {
    name: 'admin-tests',
    use: {
      ...devices['Desktop Chrome'],
      storageState: '.auth/admin.json',
    },
    dependencies: ['setup'],
  },
  {
    name: 'user-tests',
    use: {
      ...devices['Desktop Chrome'],
      storageState: '.auth/user.json',
    },
    dependencies: ['setup'],
  },
],
```

```typescript
// e2e/auth.setup.ts
import { test as setup } from '@playwright/test';

setup('admin auth', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Email').fill('admin@test.com');
  await page.getByLabel('Password').fill('adminpass');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.context().storageState({ path: '.auth/admin.json' });
});

setup('user auth', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Email').fill('user@test.com');
  await page.getByLabel('Password').fill('userpass');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.context().storageState({ path: '.auth/user.json' });
});
```

## Tests Without Auth (Public Pages)

```typescript
// Override to skip auth for specific file
test.use({ storageState: { cookies: [], origins: [] } });

test('homepage loads for anonymous users', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Welcome' })).toBeVisible();
});
```

## Multi-Role in Single Test

```typescript
test('admin can see user profile', async ({ browser }) => {
  // Create admin context
  const adminContext = await browser.newContext({
    storageState: '.auth/admin.json',
  });
  const adminPage = await adminContext.newPage();

  // Create user context
  const userContext = await browser.newContext({
    storageState: '.auth/user.json',
  });
  const userPage = await userContext.newPage();

  // Test interaction between roles
  await adminPage.goto('/admin/users');
  await userPage.goto('/profile');

  // Cleanup
  await adminContext.close();
  await userContext.close();
});
```

## API-Based Login (Faster)

```typescript
// Skip UI login, use API directly
setup('api auth', async ({ request }) => {
  const response = await request.post('/api/auth/login', {
    data: { email: 'user@test.com', password: 'password' },
  });
  expect(response.ok()).toBeTruthy();

  // Save cookies from API response
  await request.storageState({ path: '.auth/user.json' });
});
```
