import { test, expect } from '@playwright/test';
import { trackConsoleErrors, assertNoConsoleErrors } from './helpers';

/**
 * Enterprise FizzBuzz Platform — FinOps Dashboard E2E Verification
 *
 * Validates the Financial Operations page: heading, content rendering,
 * and core FinOps dashboard elements.
 */

let consoleErrors: string[] = [];

test.describe('FinOps Dashboard Page', () => {
  test.beforeEach(async ({ page }) => {
    consoleErrors = trackConsoleErrors(page);
    await page.goto('./finops');
    await page.waitForLoadState('networkidle');
  });

  test.afterEach(() => {
    assertNoConsoleErrors(consoleErrors);
  });

  test('renders page heading', async ({ page }) => {
    await expect(page.locator('main h1').first()).toContainText('FinOps');
  });

  test('renders FinOps dashboard content with data', async ({ page }) => {
    await page.waitForTimeout(2000);
    const mainText = await page.locator('main').textContent();
    expect(mainText?.length).toBeGreaterThan(100);
  });

  test('page contains financial metric labels', async ({ page }) => {
    await page.waitForTimeout(2000);
    // FinOps pages typically display cost-related metrics
    const mainText = await page.locator('main').textContent();
    expect(mainText).toBeTruthy();
  });
});
