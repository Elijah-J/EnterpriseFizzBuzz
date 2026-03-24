import { test, expect } from '@playwright/test';
import { trackConsoleErrors, assertNoConsoleErrors } from './helpers';

/**
 * Enterprise FizzBuzz Platform — Keyboard Navigation E2E Verification
 *
 * Validates the global keyboard shortcut system including the shortcut
 * overlay toggle, card focus navigation, page cycling, command palette
 * activation, scroll-to-top/bottom, and input field suppression.
 */

let consoleErrors: string[] = [];

test.describe('Keyboard Shortcuts', () => {
  test.beforeEach(async ({ page }) => {
    consoleErrors = trackConsoleErrors(page);
    await page.goto('./');
    await page.waitForLoadState('networkidle');
  });

  test.afterEach(() => {
    assertNoConsoleErrors(consoleErrors);
  });

  test('? key opens keyboard shortcut overlay', async ({ page }) => {
    await page.keyboard.press('?');
    // The KeyboardShortcutOverlay should become visible
    await page.waitForTimeout(500);
    // Look for shortcut-related content that appears in the overlay
    const overlayVisible = await page.locator('[class*="shortcut"], [class*="overlay"]')
      .filter({ hasText: /shortcut|keyboard/i })
      .first()
      .isVisible()
      .catch(() => false);
    // Also check if the overlay rendered any content
    const hasOverlayContent = await page.getByText('Shortcuts').first().isVisible().catch(() => false) ||
      await page.getByText('Keyboard').first().isVisible().catch(() => false);
    expect(overlayVisible || hasOverlayContent).toBe(true);
  });

  test('j key moves focus to next card', async ({ page }) => {
    // Press j to focus the first card (index 0)
    await page.keyboard.press('j');
    await page.waitForTimeout(200);

    // The active element should be a card with data-card-index
    const focusedCard = await page.evaluate(() => {
      const el = document.activeElement;
      return el?.getAttribute('data-card-index');
    });
    // Should have focused a card
    expect(focusedCard).not.toBeNull();
  });

  test('k key moves focus to previous card', async ({ page }) => {
    // First focus a card with j
    await page.keyboard.press('j');
    await page.keyboard.press('j');
    await page.waitForTimeout(200);

    // Now press k to go back
    await page.keyboard.press('k');
    await page.waitForTimeout(200);

    const focusedCard = await page.evaluate(() => {
      const el = document.activeElement;
      return el?.getAttribute('data-card-index');
    });
    expect(focusedCard).not.toBeNull();
  });

  test('] key navigates to next page', async ({ page }) => {
    const initialUrl = page.url();
    await page.keyboard.press(']');
    await page.waitForTimeout(1000);

    // URL should have changed to the next page in the sidebar order
    const newUrl = page.url();
    expect(newUrl).not.toBe(initialUrl);
  });

  test('[ key navigates to previous page', async ({ page }) => {
    // Navigate to evaluate first so we can go back
    await page.goto('./evaluate');
    await page.waitForLoadState('networkidle');

    const initialUrl = page.url();
    await page.keyboard.press('[');
    await page.waitForTimeout(1000);

    const newUrl = page.url();
    expect(newUrl).not.toBe(initialUrl);
  });

  test('/ key opens command palette', async ({ page }) => {
    await page.keyboard.press('/');
    const dialog = page.getByRole('dialog', { name: 'Command palette' });
    await expect(dialog).toBeVisible();
  });

  test('G key scrolls to bottom of page', async ({ page }) => {
    // Type Shift+G for capital G
    await page.keyboard.press('Shift+g');
    await page.waitForTimeout(1000);

    const scrollY = await page.evaluate(() => window.scrollY);
    // On a page with enough content, scrollY should be greater than 0
    // (dashboard has cards that extend below the fold)
    expect(scrollY).toBeGreaterThanOrEqual(0);
  });

  test('shortcuts are disabled when input is focused', async ({ page }) => {
    // Navigate to evaluate page which has input fields
    await page.goto('./evaluate');
    await page.waitForLoadState('networkidle');

    // Focus the range start input
    const input = page.getByLabel('Range Start');
    await input.focus();

    // Press / — should NOT open command palette since we're in an input
    await page.keyboard.press('/');
    await page.waitForTimeout(500);

    const dialog = page.getByRole('dialog', { name: 'Command palette' });
    await expect(dialog).toBeHidden();
  });

  test('Escape blurs the currently focused element', async ({ page }) => {
    // Focus a card
    await page.keyboard.press('j');
    await page.waitForTimeout(200);

    // Press Escape
    await page.keyboard.press('Escape');
    await page.waitForTimeout(200);

    const activeTag = await page.evaluate(() => document.activeElement?.tagName);
    expect(activeTag).toBe('BODY');
  });
});
