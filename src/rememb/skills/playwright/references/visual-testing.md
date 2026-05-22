# Visual Testing

## Screenshots

### Capture Screenshots

```typescript
// Full page
await page.screenshot({ path: 'screenshots/home.png' });

// Full page including scrollable area
await page.screenshot({ path: 'full.png', fullPage: true });

// Specific element
await page.getByTestId('chart').screenshot({ path: 'chart.png' });

// Clip region
await page.screenshot({
  path: 'header.png',
  clip: { x: 0, y: 0, width: 1280, height: 100 },
});
```

### Auto Screenshots on Failure

```typescript
// playwright.config.ts
use: {
  screenshot: 'only-on-failure',  // or 'on', 'off'
}
```

## Visual Comparison (Snapshot Testing)

### Basic Usage

```typescript
// Full page comparison
await expect(page).toHaveScreenshot('homepage.png');

// Element comparison
await expect(page.getByTestId('chart')).toHaveScreenshot('chart.png');

// Auto-generated name (based on test name)
await expect(page).toHaveScreenshot();
```

### Key Behavior: Auto-Stabilization

`toHaveScreenshot()` takes MULTIPLE screenshots until two consecutive ones match. This handles animations, lazy loading, etc. Only then does it compare against the stored snapshot.

### Snapshot Naming

Snapshots are stored in `<test-dir>/<test-file>-snapshots/` and include browser + platform suffix:
`homepage-chromium-darwin.png`

### Tolerance Options

```typescript
await expect(page).toHaveScreenshot('dashboard.png', {
  maxDiffPixels: 100,           // Allow up to 100 different pixels
  maxDiffPixelRatio: 0.01,      // Or 1% of pixels
  threshold: 0.2,               // Per-pixel color tolerance (0-1)
  mask: [page.getByTestId('timestamp')], // Ignore dynamic content
  animations: 'disabled',       // Freeze CSS animations
});
```

### Update Snapshots

```bash
npx playwright test --update-snapshots
```

## ARIA Snapshots

Test accessibility tree structure:

```typescript
await expect(page.getByRole('list')).toMatchAriaSnapshot(`
  - listitem: Item 1
  - listitem: Item 2
  - listitem: Item 3
`);
```

### Key Behaviors

- **Order-sensitive**: Items must appear in the specified order
- **Partial matching by default**: Extra children are allowed (uses `contain` mode)
- **Strict matching**: Use `/children: equal` to require exact children

```typescript
// Strict — no extra children allowed
await expect(page.getByRole('navigation')).toMatchAriaSnapshot(`
  - navigation:
    /children: equal
    - link "Home"
    - link "About"
`);
```

### Generate ARIA Snapshots

```typescript
// Empty string generates snapshot on-the-fly (for initial creation)
await expect(page.locator('body')).toMatchAriaSnapshot('');
```

```bash
# Update ARIA snapshots
npx playwright test --update-snapshots
```

### Regex in ARIA Snapshots

```typescript
await expect(page.getByRole('list')).toMatchAriaSnapshot(`
  - listitem: /Item \\d+/
  - listitem: Item 2
`);
```

## Video Recording

```typescript
// playwright.config.ts
use: {
  video: 'retain-on-failure',  // or 'on', 'off', 'on-first-retry'
}
```

**Gotcha**: Video is only available AFTER the page/context is closed.

```typescript
// Access video path after test
test.afterEach(async ({ page }, testInfo) => {
  if (testInfo.status !== 'passed') {
    const video = page.video();
    if (video) {
      const path = await video.path();
      testInfo.attach('video', { path, contentType: 'video/webm' });
    }
  }
});
```
