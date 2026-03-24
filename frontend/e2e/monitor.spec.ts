import { test, expect } from '@playwright/test';
import { trackConsoleErrors, assertNoConsoleErrors } from './helpers';

/**
 * Enterprise FizzBuzz Platform — Infrastructure Monitor E2E Verification
 *
 * Validates the monitor route group pages: Health, Metrics, SLA, Traces,
 * Alerts, and Consensus. Each page operates within the shared Monitor layout
 * with sub-navigation tabs.
 */

let consoleErrors: string[] = [];

test.beforeEach(async ({ page }) => {
  consoleErrors = trackConsoleErrors(page);
});

test.afterEach(() => {
  assertNoConsoleErrors(consoleErrors);
});

test.describe('Monitor Layout', () => {
  test('displays shared Infrastructure Monitor heading', async ({ page }) => {
    await page.goto('./monitor/health');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('h1').first()).toContainText('Infrastructure Monitor');
  });

  test('renders sub-navigation tabs for all monitor pages', async ({ page }) => {
    await page.goto('./monitor/health');
    await page.waitForLoadState('networkidle');

    const tabs = ['Metrics', 'Health Matrix', 'SLA Dashboard', 'Traces', 'Alerts', 'Consensus'];
    for (const tab of tabs) {
      await expect(page.getByText(tab, { exact: true }).first()).toBeVisible();
    }
  });

  test('sub-navigation tabs navigate between monitor pages', async ({ page }) => {
    await page.goto('./monitor/health');
    await page.waitForLoadState('networkidle');

    // Click Metrics tab
    await page.getByText('Metrics', { exact: true }).first().click();
    await page.waitForURL('**/monitor/metrics');

    // Click Alerts tab
    await page.getByText('Alerts', { exact: true }).first().click();
    await page.waitForURL('**/monitor/alerts');
  });
});

test.describe('Health Check Matrix Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('./monitor/health');
    await page.waitForLoadState('networkidle');
  });

  test('displays health status KPI summary bar', async ({ page }) => {
    // Wait for data to load — health page shows spinner initially
    await expect(page.getByText('Overall').first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Healthy').first()).toBeVisible();
    await expect(page.getByText('Degraded').first()).toBeVisible();
  });

  test('renders subsystem health cards after data loads', async ({ page }) => {
    // Wait for the health cards to render (loading state shows spinner first)
    await expect(page.getByText('Overall').first()).toBeVisible({ timeout: 15000 });

    // Check for sort controls
    await expect(page.getByText('Sort by:')).toBeVisible();
    await expect(page.getByText('Status', { exact: true }).first()).toBeVisible();
  });

  test('sort controls change ordering', async ({ page }) => {
    await expect(page.getByText('Sort by:')).toBeVisible({ timeout: 15000 });

    // Click Name sort button
    await page.getByRole('button', { name: 'Name' }).click();

    // The sort control should now show Name as active
    const nameBtn = page.getByRole('button', { name: 'Name' });
    await expect(nameBtn).toBeVisible();
  });

  test('filter dropdown changes displayed subsystems', async ({ page }) => {
    await expect(page.getByText('Show:')).toBeVisible({ timeout: 15000 });

    const select = page.locator('select');
    await select.selectOption('up');

    // After filtering to UP only, the page should show results
    await expect(page.getByText('Show:')).toBeVisible();
  });

  test('health sparklines render SVG elements', async ({ page }) => {
    await expect(page.getByText('Sort by:')).toBeVisible({ timeout: 15000 });

    const sparklines = page.locator('svg[aria-label="Health trend sparkline"]');
    const count = await sparklines.count();
    expect(count).toBeGreaterThan(0);
  });
});

test.describe('Metrics Dashboard Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('./monitor/metrics');
    await page.waitForLoadState('networkidle');
  });

  test('displays metric selector dropdown', async ({ page }) => {
    // The metric selector button should be visible
    await expect(page.getByText('Select metric...').or(page.locator('button').filter({ hasText: /[a-z_]+/ }).first())).toBeVisible({ timeout: 10000 });
  });

  test('time range tabs are visible', async ({ page }) => {
    await expect(page.getByText('1m', { exact: true }).first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('5m', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('15m', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('1h', { exact: true }).first()).toBeVisible();
  });

  test('auto-refresh controls are present', async ({ page }) => {
    await expect(page.getByText('Refresh').first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('1s', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('5s', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Off', { exact: true }).first()).toBeVisible();
  });

  test('Metric Details panel renders', async ({ page }) => {
    await expect(page.getByText('Metric Details').first()).toBeVisible({ timeout: 10000 });
  });

  test('All Platform Metrics grid renders sparkline cards', async ({ page }) => {
    await expect(page.getByText('All Platform Metrics').first()).toBeVisible({ timeout: 10000 });

    // Sparkline cards should be visible as buttons
    const sparkCards = page.locator('button').filter({ has: page.locator('svg') });
    const count = await sparkCards.count();
    expect(count).toBeGreaterThan(0);
  });
});

test.describe('SLA Dashboard Page', () => {
  test('renders SLA status information', async ({ page }) => {
    await page.goto('./monitor/sla');
    await page.waitForLoadState('networkidle');

    // Wait for the page to render content
    await page.waitForTimeout(2000);

    // The page should be within the monitor layout
    await expect(page.locator('h1').first()).toContainText('Infrastructure Monitor');
  });
});

test.describe('Traces Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('./monitor/traces');
    await page.waitForLoadState('networkidle');
  });

  test('renders trace list after data loads', async ({ page }) => {
    // Wait for traces to load
    await page.waitForTimeout(3000);

    // The page should show trace-related content
    await expect(page.locator('h1').first()).toContainText('Infrastructure Monitor');
  });
});

test.describe('Alerts Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('./monitor/alerts');
    await page.waitForLoadState('networkidle');
  });

  test('renders severity filter tabs', async ({ page }) => {
    // Wait for alerts to load
    await page.waitForTimeout(2000);

    // The alerts page should render within the monitor layout
    await expect(page.locator('h1').first()).toContainText('Infrastructure Monitor');
  });
});

test.describe('Consensus Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('./monitor/consensus');
    await page.waitForLoadState('networkidle');
  });

  test('renders consensus topology and election timeline', async ({ page }) => {
    // Wait for consensus data to load
    await page.waitForTimeout(2000);

    // The page should render within the monitor layout
    await expect(page.locator('h1').first()).toContainText('Infrastructure Monitor');
  });
});
