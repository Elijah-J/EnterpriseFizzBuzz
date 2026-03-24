import { test, expect } from '@playwright/test';
import { trackConsoleErrors, assertNoConsoleErrors } from './helpers';

/**
 * Enterprise FizzBuzz Platform — Platform Pages E2E Verification
 *
 * Validates the platform subsystem pages: Cache Coherence, Compliance,
 * Blockchain, Analytics, Configuration, Audit Log, Chaos Engineering,
 * and Digital Twin.
 */

let consoleErrors: string[] = [];

test.beforeEach(async ({ page }) => {
  consoleErrors = trackConsoleErrors(page);
});

test.afterEach(() => {
  assertNoConsoleErrors(consoleErrors);
});

test.describe('Cache Coherence Page', () => {
  test('renders page heading and content', async ({ page }) => {
    await page.goto('./cache');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('main h1').first()).toContainText('Cache Coherence');
  });

  test('renders cache-related content after data loads', async ({ page }) => {
    await page.goto('./cache');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    const mainText = await page.locator('main').textContent();
    expect(mainText?.length).toBeGreaterThan(100);
  });
});

test.describe('Compliance Page', () => {
  test('renders page heading', async ({ page }) => {
    await page.goto('./compliance');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('main h1').first()).toContainText('Compliance');
  });

  test('renders compliance framework content', async ({ page }) => {
    await page.goto('./compliance');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    const mainText = await page.locator('main').textContent();
    expect(mainText?.length).toBeGreaterThan(100);
  });
});

test.describe('Blockchain Page', () => {
  test('renders page heading', async ({ page }) => {
    await page.goto('./blockchain');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('main h1').first()).toContainText('Blockchain');
  });

  test('renders blockchain ledger content', async ({ page }) => {
    await page.goto('./blockchain');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    const mainText = await page.locator('main').textContent();
    expect(mainText?.length).toBeGreaterThan(100);
  });
});

test.describe('Analytics Page', () => {
  test('renders page heading', async ({ page }) => {
    await page.goto('./analytics');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('main h1').first()).toContainText('Analytics');
  });

  test('renders analytics dashboard content', async ({ page }) => {
    await page.goto('./analytics');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    const mainText = await page.locator('main').textContent();
    expect(mainText?.length).toBeGreaterThan(100);
  });
});

test.describe('Configuration Page', () => {
  test('renders page heading', async ({ page }) => {
    await page.goto('./configuration');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('main h1').first()).toContainText('Configuration');
  });

  test('renders configuration management content', async ({ page }) => {
    await page.goto('./configuration');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    const mainText = await page.locator('main').textContent();
    expect(mainText?.length).toBeGreaterThan(100);
  });
});

test.describe('Audit Log Page', () => {
  test('renders page heading', async ({ page }) => {
    await page.goto('./audit');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('main h1').first()).toContainText('Audit');
  });

  test('renders audit log content', async ({ page }) => {
    await page.goto('./audit');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    const mainText = await page.locator('main').textContent();
    expect(mainText?.length).toBeGreaterThan(100);
  });
});

test.describe('Chaos Engineering Page', () => {
  test('renders chaos engineering loading or content state', async ({ page }) => {
    await page.goto('./chaos');
    await page.waitForLoadState('networkidle');
    // The chaos page may show a loading indicator while data is fetched.
    // Verify the page rendered something — either the heading or the
    // loading message.
    const hasHeading = await page.locator('main h1').first().isVisible({ timeout: 5000 }).catch(() => false);
    if (hasHeading) {
      const text = await page.locator('main h1').first().textContent();
      expect(text).toMatch(/Chaos/);
    } else {
      // Accept loading state as valid render
      const bodyText = await page.locator('body').textContent();
      expect(bodyText).toContain('chaos');
    }
  });
});

test.describe('Digital Twin Page', () => {
  test('renders page heading', async ({ page }) => {
    await page.goto('./digital-twin');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('main h1').first()).toContainText('Digital Twin');
  });

  test('renders digital twin content', async ({ page }) => {
    await page.goto('./digital-twin');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    const mainText = await page.locator('main').textContent();
    expect(mainText?.length).toBeGreaterThan(100);
  });
});
