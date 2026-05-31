---
name: playwright-skill
description: Complete browser automation with Playwright. Test pages, fill forms, take screenshots, check responsive design, validate UX, test login flows, check links, and automate browser tasks. Use when the user wants browser-based testing or scripted web automation.
---

# Playwright Browser Automation

## Overview

Use this skill to write and run focused Playwright scripts for testing or automating websites. Keep the main flow independent of any specific host or launcher. Choose the execution surface that already exists in the current environment.

## When to Use

Use this skill when the user wants to:

- test a web page or flow in a real browser
- take screenshots or verify responsive layouts
- automate form filling or navigation
- validate login, checkout, or dashboard behavior
- inspect broken links or page content with scripted checks

## Core Workflow

1. Identify the target URL.
2. If the target is local, check whether a development server is already running.
3. Write a temporary Playwright script outside the repository or in another disposable location.
4. Parameterize the target URL and any secrets instead of hardcoding them.
5. Run the script using the available Playwright runtime in the current environment.
6. Collect artifacts such as screenshots, logs, and assertion results.
7. Clean up temporary files when they are no longer needed.

Use a visible browser by default unless the user explicitly asks for headless execution.

## Inputs / Assumptions

- A reachable URL is required before the script runs.
- Localhost testing should confirm the correct port first.
- Credentials and secrets should come from environment variables or explicit user input, never from hardcoded literals.
- Temporary scripts should not clutter the project unless the user asks to keep them.

## Examples

### Basic page check

```javascript
const { chromium } = require('playwright');

const TARGET_URL = process.env.TARGET_URL ?? 'http://localhost:3000';

(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();

  await page.goto(TARGET_URL, { waitUntil: 'domcontentloaded' });
  console.log('Title:', await page.title());
  await page.screenshot({ path: '/tmp/page-check.png', fullPage: true });

  await browser.close();
})();
```

### Login flow

```javascript
const { chromium } = require('playwright');

const TARGET_URL = process.env.TARGET_URL ?? 'http://localhost:3000';
const TEST_PASSWORD = process.env.TEST_PASSWORD;

(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();

  await page.goto(`${TARGET_URL}/login`);
  await page.fill('input[name="email"]', 'user@domain.test');
  await page.fill('input[name="password"]', TEST_PASSWORD ?? '<secret>');
  await page.click('button[type="submit"]');
  await page.waitForURL('**/dashboard');

  console.log('Login flow passed');
  await browser.close();
})();
```

### Responsive capture

```javascript
const { chromium } = require('playwright');

const TARGET_URL = process.env.TARGET_URL ?? 'http://localhost:3000';

(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();

  for (const viewport of [
    { name: 'desktop', width: 1440, height: 900 },
    { name: 'tablet', width: 768, height: 1024 },
    { name: 'mobile', width: 390, height: 844 },
  ]) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto(TARGET_URL, { waitUntil: 'domcontentloaded' });
    await page.screenshot({ path: `/tmp/${viewport.name}.png`, fullPage: true });
  }

  await browser.close();
})();
```

## Optional Host Notes

- If the current environment already exposes browser automation tools, use those when they are faster than writing a fresh Playwright script.
- If this skill is bundled with helper scripts such as a local runner or server detector, treat them as optional accelerators rather than required infrastructure.
- If the current project already has Playwright configured, prefer the existing config, fixtures, and test runner over an ad hoc launcher.

## Validation Checklist

- The target URL was confirmed before execution
- The script used placeholders or environment variables for configurable values
- Secrets were not hardcoded
- Temporary files were written outside the main project unless the user requested otherwise
- Screenshots, logs, or assertions were captured to confirm the result
## Best Practices

Follow the constraints, conventions, and cautions documented below, and prefer the documented path over improvisation.

## References

Use any linked scripts, assets, reference files, and companion resources mentioned in this document.

