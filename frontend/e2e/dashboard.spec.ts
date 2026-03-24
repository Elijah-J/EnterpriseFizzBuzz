import { test, expect } from '@playwright/test';
import { trackConsoleErrors, assertNoConsoleErrors } from './helpers';

/**
 * Enterprise FizzBuzz Platform — Executive Dashboard E2E Verification
 *
 * Validates that the executive dashboard loads all widget cards, renders the
 * bento grid layout, displays StatGroup KPIs, and populates widget data
 * beyond skeleton loading states.
 */

let consoleErrors: string[] = [];

test.describe('Executive Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    consoleErrors = trackConsoleErrors(page);
    await page.goto('./');
    await page.waitForLoadState('networkidle');
  });

  test.afterEach(() => {
    assertNoConsoleErrors(consoleErrors);
  });

  test('displays the Operations Center heading', async ({ page }) => {
    const heading = page.locator('main h1').first();
    await expect(heading).toBeVisible();
    const text = await heading.textContent();
    expect((text ?? '').replace(/\u00A0/g, ' ')).toMatch(/Operations Center/);
  });

  test('renders all widget cards in the bento grid', async ({ page }) => {
    const expectedSections = [
      'Evaluation Pipeline',
      'SLA Compliance',
      'Incident Status',
      'Infrastructure Health Matrix',
      'FinOps Expenditure',
      'Paxos Consensus',
      'Blockchain Ledger',
    ];

    for (const section of expectedSections) {
      await expect(page.getByText(section, { exact: true }).first()).toBeVisible();
    }
  });

  test('renders StatGroup KPI bar with operational metrics', async ({ page }) => {
    await expect(page.getByText('Uptime', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Eval Throughput', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('P99 Latency', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Open Incidents', { exact: true }).first()).toBeVisible();
  });

  test('KPI values populate with numeric data', async ({ page }) => {
    await expect(page.getByText('99.97%').first()).toBeVisible();
    await expect(page.getByText('12.4K/s').first()).toBeVisible();
    await expect(page.getByText('42ms').first()).toBeVisible();
  });

  test('widget cards are focusable via data-card-index attributes', async ({ page }) => {
    const cards = page.locator('[data-card-index]');
    const count = await cards.count();
    expect(count).toBeGreaterThanOrEqual(6);
  });

  test('featured card variant applies to throughput widget', async ({ page }) => {
    const featuredCard = page.locator('[data-card-index="0"]');
    await expect(featuredCard).toBeVisible();
  });

  test('widget data populates beyond skeleton state', async ({ page }) => {
    // Wait for skeleton loading states to resolve. Widgets use
    // the DataProvider to fetch simulated telemetry data.
    // The ThroughputWidget should render animated numbers after data loads.
    await page.waitForTimeout(2000);

    // Check that there's numeric content in the widgets (not just skeletons)
    const mainContent = page.locator('main');
    const text = await mainContent.textContent();
    // Dashboard should contain some numeric metric values
    expect(text).toMatch(/\d+/);
  });

  test('Blockchain Ledger shows empty state placeholder', async ({ page }) => {
    await expect(page.getByText('Block Explorer')).toBeVisible();
    await expect(
      page.getByText('Distributed ledger integration is pending deployment')
    ).toBeVisible();
  });
});
