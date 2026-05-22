# Locators & Actions

## Locator Priority (Best → Worst)

```typescript
// 1. Role-based (BEST — accessible, resilient)
page.getByRole('button', { name: 'Submit' })
page.getByRole('textbox', { name: 'Email' })
page.getByRole('link', { name: 'Sign up' })
page.getByRole('heading', { name: 'Welcome', level: 1 })
page.getByRole('checkbox', { name: 'Remember me' })
page.getByRole('combobox', { name: 'Country' })

// 2. Label/placeholder (forms)
page.getByLabel('Email address')
page.getByPlaceholder('Enter your email')

// 3. Test IDs (stable, explicit)
page.getByTestId('submit-button')

// 4. Text content
page.getByText('Welcome back')
page.getByText(/welcome/i)

// 5. CSS/XPath (AVOID — brittle)
page.locator('.btn-primary')
```

## Filtering & Chaining

```typescript
// Narrow to a section
const form = page.getByRole('form', { name: 'Login' });
await form.getByRole('textbox', { name: 'Email' }).fill('user@test.com');

// Filter by text
page.getByRole('listitem').filter({ hasText: 'Product A' });

// Filter by child locator (MUST be relative to the original locator)
page.getByRole('listitem').filter({
  has: page.getByRole('button', { name: 'Delete' })
});

// Filter by NOT having
page.getByRole('listitem').filter({
  hasNot: page.getByText('Sold out')
});

// Chain locators
page.getByTestId('product-card').getByRole('button', { name: 'Buy' });
```

### Gotcha: `has:` Filter is Relative

The `has:` locator searches WITHIN the matched element. Filtering by a parent element won't work — it must be a descendant.

### Gotcha: `has-text` CSS Pseudo-Class

```typescript
// ❌ BAD — matches <body> and everything
page.locator(':has-text("Submit")')

// ✅ GOOD — combine with element selector
page.locator('div:has-text("Submit")')
```

## Actionability Checks

Each action has specific pre-checks. Key differences:

| Action | Visible | Stable | Enabled | Editable | Receives Events |
|--------|---------|--------|---------|----------|-----------------|
| `click()` | ✅ | ✅ | ✅ | — | ✅ |
| `fill()` | ✅ | — | ✅ | ✅ | — |
| `check()` | ✅ | ✅ | ✅ | — | ✅ |
| `selectOption()` | ✅ | ✅ | ✅ | — | ✅ |
| `press()` | — | — | — | — | — |
| `pressSequentially()` | — | — | — | — | — |
| `setInputFiles()` | ✅ | — | ✅ | — | — |

**Key insight**: `press()` and `pressSequentially()` have NO actionability checks. `fill()` skips Stable and Receives Events checks.

### Visibility Rules

- `opacity: 0` → **visible** (still occupies layout space)
- Zero width or height → **not visible**
- `visibility: hidden` → **not visible**
- `display: none` → **not visible**

### Stability

Element must maintain the same bounding box for at least two consecutive animation frames.

## Input Actions

### Text Input

```typescript
// fill() — clears then sets value, fires 'input' and 'change'
await page.getByLabel('Email').fill('user@test.com');

// clear()
await page.getByLabel('Email').clear();

// pressSequentially() — types character by character (for special input handling)
await page.getByLabel('Code').pressSequentially('123456', { delay: 100 });

// Keyboard shortcuts
await page.getByLabel('Text').press('Control+a');
await page.keyboard.press('Enter');
```

### Select / Checkbox / Radio

```typescript
// Select by value, label, or element
await page.getByLabel('Color').selectOption('blue');
await page.getByLabel('Color').selectOption({ label: 'Blue' });
await page.getByLabel('Color').selectOption(['red', 'green']); // multi-select

// Checkbox/Radio
await page.getByRole('checkbox', { name: 'Terms' }).check();
await page.getByRole('checkbox', { name: 'Terms' }).uncheck();
await page.getByRole('radio', { name: 'Option A' }).check();
```

### File Upload

```typescript
// Single file
await page.getByLabel('Upload').setInputFiles('file.pdf');

// Multiple files
await page.getByLabel('Upload').setInputFiles(['file1.pdf', 'file2.pdf']);

// Remove files
await page.getByLabel('Upload').setInputFiles([]);

// No input element — use filechooser event
const fileChooserPromise = page.waitForEvent('filechooser');
await page.getByRole('button', { name: 'Upload' }).click();
const fileChooser = await fileChooserPromise;
await fileChooser.setFiles('myfile.pdf');
```

### Drag and Drop

```typescript
// Simple drag
await page.getByTestId('source').dragTo(page.getByTestId('target'));

// Manual drag (needed when dragover events must fire)
await page.getByTestId('source').hover();
await page.mouse.down();
await page.getByTestId('target').hover();
await page.mouse.move(0, 0); // Second move needed for dragover in all browsers
await page.mouse.up();
```

## Handling Multiple Elements

```typescript
const items = page.getByRole('listitem');
await expect(items).toHaveCount(5);

// Get specific
await items.nth(0).click();
await items.first().click();
await items.last().click();

// Iterate
for (const item of await items.all()) {
  console.log(await item.textContent());
}
```

## Shadow DOM

All Playwright locators pierce Shadow DOM by default EXCEPT XPath.

```typescript
// ✅ These work through shadow DOM
page.getByRole('button', { name: 'Submit' })
page.getByTestId('my-component')
page.locator('css:light(.my-class') // opt-out of shadow piercing
```
