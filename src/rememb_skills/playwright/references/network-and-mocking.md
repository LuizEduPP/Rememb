# Network & Mocking

## Route Interception

### Mock API Response

```typescript
test('shows users', async ({ page }) => {
  await page.route('**/api/users', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        { id: 1, name: 'Alice' },
        { id: 2, name: 'Bob' },
      ]),
    })
  );

  await page.goto('/users');
  await expect(page.getByText('Alice')).toBeVisible();
});
```

### Mock Error Responses

```typescript
await page.route('**/api/users', route =>
  route.fulfill({
    status: 500,
    body: JSON.stringify({ error: 'Server error' }),
  })
);
```

### Modify Real Response

```typescript
await page.route('**/api/products', async route => {
  const response = await route.fetch();
  const json = await response.json();
  json.products = json.products.map(p => ({ ...p, price: p.price * 0.9 }));
  await route.fulfill({ json });
});
```

### Conditional Routing

```typescript
await page.route('**/api/**', route => {
  if (route.request().url().includes('/api/users')) {
    return route.fulfill({ status: 200, json: [{ id: 1, name: 'Mock' }] });
  }
  return route.continue(); // Pass through to real server
});
```

### Abort Requests

```typescript
// Block images for faster tests
await page.route('**/*.{png,jpg,jpeg,gif,svg}', route => route.abort());
```

### Network Delay Simulation

```typescript
await page.route('**/api/**', async route => {
  await new Promise(r => setTimeout(r, 3000));
  await route.continue();
});
```

## Waiting for Responses

```typescript
// Wait for specific response
const responsePromise = page.waitForResponse('**/api/users');
await page.getByRole('button', { name: 'Load' }).click();
const response = await responsePromise;
expect(response.status()).toBe(200);

// Wait with predicate
const response = await page.waitForResponse(
  r => r.url().includes('/api/data') && r.status() === 200
);
```

## HAR File Recording & Playback

```typescript
// Record API responses to HAR file
await page.routeFromHAR('mocks/api.har', {
  url: '**/api/**',
  update: true,
});

// Playback recorded responses
await page.routeFromHAR('mocks/api.har', {
  url: '**/api/**',
  update: false,
});
```

```bash
# Record HAR via CLI
npx playwright open --save-har=mocks/api.har http://localhost:3000
```

## API Testing (No Browser)

Use `request` fixture for direct API testing without a browser:

```typescript
import { test, expect } from '@playwright/test';

test('create and retrieve user', async ({ request }) => {
  // POST
  const createResponse = await request.post('/api/users', {
    data: { name: 'John', email: 'john@test.com' },
  });
  expect(createResponse.ok()).toBeTruthy();
  const user = await createResponse.json();

  // GET
  const getResponse = await request.get(`/api/users/${user.id}`);
  expect(getResponse.ok()).toBeTruthy();
  const fetched = await getResponse.json();
  expect(fetched.name).toBe('John');

  // DELETE (cleanup)
  await request.delete(`/api/users/${user.id}`);
});
```

### Shared API Context

```typescript
// Share cookies/auth across API requests
const apiContext = await request.newContext({
  baseURL: 'http://localhost:3000',
  extraHTTPHeaders: {
    Authorization: `Bearer ${token}`,
  },
});

const response = await apiContext.get('/api/protected');
```

## Glob Patterns for Routes

- `*` matches any characters except `/`
- `**` matches any characters including `/`
- `?` matches literal `?` only (NOT single char wildcard)

```typescript
// Match any API path
await page.route('**/api/**', handler);

// Match specific endpoint
await page.route('**/api/users/*', handler);
```

## WebSocket Mocking

```typescript
await page.routeWebSocket('<websocket-url>', ws => {
  ws.onMessage(msg => {
    if (msg === 'ping') ws.send('pong');
  });
});
```
