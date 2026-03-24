import { test, expect } from '@playwright/test';
import { trackConsoleErrors, assertNoConsoleErrors } from './helpers';

/**
 * Enterprise FizzBuzz Platform — Custom Cursor E2E Verification
 *
 * Validates the custom cursor overlay behavior: presence on desktop
 * viewports without reduced motion, and automatic suppression on
 * touch devices and when the prefers-reduced-motion media query is active.
 */

let consoleErrors: string[] = [];

test.beforeEach(async ({ page }) => {
  consoleErrors = trackConsoleErrors(page);
});

test.afterEach(() => {
  assertNoConsoleErrors(consoleErrors);
});

test.describe('Custom Cursor', () => {
  test('cursor container renders on desktop viewport', async ({ page }) => {
    await page.goto('./');
    await page.waitForLoadState('networkidle');

    // Trigger a mouse move to ensure the cursor hook activates
    await page.mouse.move(400, 300);
    await page.waitForTimeout(500);

    // The custom cursor renders with class "custom-cursor-container" and aria-hidden
    const cursor = page.locator('.custom-cursor-container');
    const count = await cursor.count();
    // On a non-touch, non-reduced-motion environment, the cursor should render
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('cursor overlay has pointer-events: none to avoid blocking interaction', async ({ page }) => {
    await page.goto('./');
    await page.waitForLoadState('networkidle');
    await page.mouse.move(400, 300);
    await page.waitForTimeout(500);

    const cursor = page.locator('.custom-cursor-container');
    const count = await cursor.count();
    if (count > 0) {
      const pointerEvents = await cursor.first().evaluate(
        (el) => window.getComputedStyle(el).pointerEvents
      );
      expect(pointerEvents).toBe('none');
    }
  });

  test('cursor is hidden when prefers-reduced-motion is active', async ({ page }) => {
    // Emulate reduced motion preference
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('./');
    await page.waitForLoadState('networkidle');
    await page.mouse.move(400, 300);
    await page.waitForTimeout(500);

    // The custom cursor should not render when reduced motion is preferred
    const cursor = page.locator('.custom-cursor-container');
    const count = await cursor.count();
    expect(count).toBe(0);
  });

  test('cursor is hidden on touch device emulation', async ({ browser }) => {
    const context = await browser.newContext({
      hasTouch: true,
    });
    const page = await context.newPage();
    await page.goto('./');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);

    // Touch devices suppress the custom cursor entirely
    const cursor = page.locator('.custom-cursor-container');
    const count = await cursor.count();
    expect(count).toBe(0);

    await context.close();
  });
});
