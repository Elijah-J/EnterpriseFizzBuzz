import { test, expect } from '@playwright/test';
import { trackConsoleErrors, assertNoConsoleErrors } from './helpers';

/**
 * Enterprise FizzBuzz Platform — Research Pages E2E Verification
 *
 * Validates the research route group: Quantum Workbench, Evolution
 * Observatory, Federated Learning, and Archaeological Recovery.
 */

let consoleErrors: string[] = [];

test.beforeEach(async ({ page }) => {
  consoleErrors = trackConsoleErrors(page);
});

test.afterEach(() => {
  assertNoConsoleErrors(consoleErrors);
});

test.describe('Quantum Workbench Page', () => {
  test('renders page heading', async ({ page }) => {
    await page.goto('./quantum');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('main h1').first()).toContainText('Quantum');
  });

  test('renders quantum simulation content', async ({ page }) => {
    await page.goto('./quantum');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    const mainText = await page.locator('main').textContent();
    expect(mainText?.length).toBeGreaterThan(100);
  });
});

test.describe('Evolution Observatory Page', () => {
  test('renders page heading', async ({ page }) => {
    await page.goto('./evolution');
    await page.waitForLoadState('networkidle');
    const heading = page.locator('main h1').first();
    await expect(heading).toBeVisible();
    const text = await heading.textContent();
    const normalized = (text ?? '').replace(/\u00A0/g, ' ');
    expect(normalized).toMatch(/Genetic Algorithm Observatory|Evolution/);
  });

  test('renders evolution content', async ({ page }) => {
    await page.goto('./evolution');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    const mainText = await page.locator('main').textContent();
    expect(mainText?.length).toBeGreaterThan(100);
  });
});

test.describe('Federated Learning Page', () => {
  test('renders page heading', async ({ page }) => {
    await page.goto('./federated-learning');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('main h1').first()).toContainText('Federated Learning');
  });

  test('renders federated learning content', async ({ page }) => {
    await page.goto('./federated-learning');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    const mainText = await page.locator('main').textContent();
    expect(mainText?.length).toBeGreaterThan(100);
  });
});

test.describe('Archaeological Recovery Page', () => {
  test('renders page heading', async ({ page }) => {
    await page.goto('./archaeology');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('main h1').first()).toContainText('Archaeolog');
  });

  test('renders archaeology content', async ({ page }) => {
    await page.goto('./archaeology');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    const mainText = await page.locator('main').textContent();
    expect(mainText?.length).toBeGreaterThan(100);
  });
});
