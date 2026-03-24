import { test, expect, type Page } from '@playwright/test';
import { trackConsoleErrors, assertNoConsoleErrors } from './helpers';

/**
 * Enterprise FizzBuzz Platform — Widget Data Flow Verification
 *
 * For each data-driven widget on the dashboard and key subsystem pages,
 * verifies that components transition from their initial loading/skeleton
 * state to rendering real data. This catches silent data provider failures
 * where a widget renders its chrome but never populates with telemetry.
 *
 * Each test:
 *   1. Registers error listeners before navigation
 *   2. Navigates to the page
 *   3. Confirms either a loading indicator appears or data renders immediately
 *   4. Waits for the data to fully populate
 *   5. Asserts specific data markers (numbers, labels, charts) are present
 *   6. Asserts zero console errors
 */

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setupListeners(page: Page): { consoleErrors: string[]; uncaughtErrors: string[] } {
  const consoleErrors = trackConsoleErrors(page);
  const uncaughtErrors: string[] = [];
  page.on('pageerror', (error) => {
    uncaughtErrors.push(error.message);
  });
  return { consoleErrors, uncaughtErrors };
}

function assertClean(consoleErrors: string[], uncaughtErrors: string[]): void {
  assertNoConsoleErrors(consoleErrors);
  const real = uncaughtErrors.filter(
    (e) =>
      !e.includes('ResizeObserver') &&
      !e.includes('Loading chunk') &&
      !e.includes('ChunkLoadError'),
  );
  expect(real, 'Uncaught page exceptions detected').toHaveLength(0);
}

// ---------------------------------------------------------------------------
// Dashboard Widget Tests
// ---------------------------------------------------------------------------

test.describe('Dashboard widget data flow', () => {
  test('Throughput widget populates with animated numeric data', async ({ page }) => {
    const { consoleErrors, uncaughtErrors } = setupListeners(page);
    await page.goto('./');

    // Wait for the Operations Center heading
    await page.getByRole('heading', { level: 1, name: /operations center/i }).waitFor({ timeout: 10_000 });

    // The Evaluation Pipeline card should be visible
    await expect(page.getByText('Evaluation Pipeline')).toBeVisible();

    // Wait for throughput widget to populate beyond skeleton
    await page.waitForTimeout(3000);

    // The featured card should contain numeric content from DataProvider
    const heroCard = page.locator('[data-card-index="0"]');
    await expect(heroCard).toBeVisible();
    const heroText = await heroCard.textContent();
    expect(heroText).toMatch(/\d/);

    assertClean(consoleErrors, uncaughtErrors);
  });

  test('SLA Budget widget renders compliance data', async ({ page }) => {
    const { consoleErrors, uncaughtErrors } = setupListeners(page);
    await page.goto('./');
    await page.getByRole('heading', { level: 1, name: /operations center/i }).waitFor({ timeout: 10_000 });

    await expect(page.getByText('SLA Compliance')).toBeVisible();
    const slaCard = page.locator('[data-card-index="1"]');
    await expect(slaCard).toBeVisible();

    // Wait for data to populate
    await page.waitForTimeout(3000);
    const text = await slaCard.textContent();
    expect(text?.length, 'SLA card should have content beyond the heading').toBeGreaterThan(10);

    assertClean(consoleErrors, uncaughtErrors);
  });

  test('Incidents widget renders incident data', async ({ page }) => {
    const { consoleErrors, uncaughtErrors } = setupListeners(page);
    await page.goto('./');
    await page.getByRole('heading', { level: 1, name: /operations center/i }).waitFor({ timeout: 10_000 });

    await expect(page.getByText('Incident Status')).toBeVisible();
    const card = page.locator('[data-card-index="2"]');
    await expect(card).toBeVisible();

    await page.waitForTimeout(3000);
    const text = await card.textContent();
    expect(text?.length).toBeGreaterThan(10);

    assertClean(consoleErrors, uncaughtErrors);
  });

  test('Health Matrix widget renders subsystem grid', async ({ page }) => {
    const { consoleErrors, uncaughtErrors } = setupListeners(page);
    await page.goto('./');
    await page.getByRole('heading', { level: 1, name: /operations center/i }).waitFor({ timeout: 10_000 });

    await expect(page.getByText('Infrastructure Health Matrix')).toBeVisible();
    const card = page.locator('[data-card-index="3"]');
    await expect(card).toBeVisible();

    await page.waitForTimeout(3000);
    const text = await card.textContent();
    expect(text?.length).toBeGreaterThan(20);

    assertClean(consoleErrors, uncaughtErrors);
  });

  test('FinOps Expenditure widget renders cost data', async ({ page }) => {
    const { consoleErrors, uncaughtErrors } = setupListeners(page);
    await page.goto('./');
    await page.getByRole('heading', { level: 1, name: /operations center/i }).waitFor({ timeout: 10_000 });

    await expect(page.getByText('FinOps Expenditure')).toBeVisible();
    const card = page.locator('[data-card-index="4"]');
    await expect(card).toBeVisible();

    await page.waitForTimeout(3000);
    const text = await card.textContent();
    expect(text?.length).toBeGreaterThan(10);

    assertClean(consoleErrors, uncaughtErrors);
  });

  test('Paxos Consensus widget renders state data', async ({ page }) => {
    const { consoleErrors, uncaughtErrors } = setupListeners(page);
    await page.goto('./');
    await page.getByRole('heading', { level: 1, name: /operations center/i }).waitFor({ timeout: 10_000 });

    await expect(page.getByText('Paxos Consensus')).toBeVisible();
    const card = page.locator('[data-card-index="5"]');
    await expect(card).toBeVisible();

    await page.waitForTimeout(3000);
    const text = await card.textContent();
    expect(text?.length).toBeGreaterThan(10);

    assertClean(consoleErrors, uncaughtErrors);
  });

  test('StatGroup KPI bar populates with numeric values', async ({ page }) => {
    const { consoleErrors, uncaughtErrors } = setupListeners(page);
    await page.goto('./');
    await page.getByRole('heading', { level: 1, name: /operations center/i }).waitFor({ timeout: 10_000 });

    // The KPI summary should have real data, not placeholders
    await expect(page.getByText('99.97%').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('12.4K/s').first()).toBeVisible();
    await expect(page.getByText('42ms').first()).toBeVisible();

    assertClean(consoleErrors, uncaughtErrors);
  });

  test('Blockchain Ledger card renders empty state correctly', async ({ page }) => {
    const { consoleErrors, uncaughtErrors } = setupListeners(page);
    await page.goto('./');
    await page.getByRole('heading', { level: 1, name: /operations center/i }).waitFor({ timeout: 10_000 });

    await expect(page.getByText('Blockchain Ledger')).toBeVisible();
    await expect(page.getByText('Block Explorer')).toBeVisible();
    await expect(
      page.getByText('Distributed ledger integration is pending deployment'),
    ).toBeVisible();

    assertClean(consoleErrors, uncaughtErrors);
  });
});

// ---------------------------------------------------------------------------
// Health Check Matrix Data Flow
// ---------------------------------------------------------------------------

test.describe('Health Check Matrix data flow', () => {
  test('transitions from loading spinner to populated health cards', async ({ page }) => {
    const { consoleErrors, uncaughtErrors } = setupListeners(page);
    await page.goto('./monitor/health');

    // The page shows a spinner while data is loading
    // Then transitions to showing the health card grid
    await expect(page.getByText('Overall').first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('Healthy').first()).toBeVisible();

    // Verify health cards rendered with status indicator labels.
    // The health page renders each subsystem's status as an uppercase label
    // (UP, DEGRADED, DOWN, UNKNOWN) inside a <span>. At least one must be
    // present once the data has loaded.
    const upLabel = page.getByText('UP', { exact: true }).first();
    const degradedLabel = page.getByText('DEGRADED', { exact: true }).first();
    const downLabel = page.getByText('DOWN', { exact: true }).first();
    await expect(
      upLabel.or(degradedLabel).or(downLabel),
    ).toBeAttached({ timeout: 10_000 });

    // SVG sparklines should be present
    const sparklines = page.locator('svg[aria-label="Health trend sparkline"]');
    const count = await sparklines.count();
    expect(count, 'Health sparklines should render for subsystems').toBeGreaterThan(0);

    assertClean(consoleErrors, uncaughtErrors);
  });
});

// ---------------------------------------------------------------------------
// Cache Coherence Data Flow
// ---------------------------------------------------------------------------

test.describe('Cache Coherence data flow', () => {
  test('transitions from loading state to populated cache stats', async ({ page }) => {
    const { consoleErrors, uncaughtErrors } = setupListeners(page);
    await page.goto('./cache');

    // Wait for the cache page to fully load
    await expect(page.getByText('Hit Rate').first()).toBeVisible({ timeout: 15_000 });

    // Stats summary should contain numeric data
    await expect(page.getByText('Miss Rate').first()).toBeVisible();
    await expect(page.getByText('Total Requests').first()).toBeVisible();
    await expect(page.getByText('Live Entries').first()).toBeVisible();

    // The donut chart SVG should be rendered
    const svgElements = page.locator('main svg');
    const svgCount = await svgElements.count();
    expect(svgCount, 'SVG chart elements should render in cache view').toBeGreaterThan(0);

    assertClean(consoleErrors, uncaughtErrors);
  });

  test('cache line inventory table populates with rows', async ({ page }) => {
    const { consoleErrors, uncaughtErrors } = setupListeners(page);
    await page.goto('./cache');

    await expect(page.getByText('Hit Rate').first()).toBeVisible({ timeout: 15_000 });

    // Switch to Cache Lines tab
    const cacheLineTab = page.getByText('Cache Lines', { exact: true }).first();
    if (await cacheLineTab.isVisible().catch(() => false)) {
      await cacheLineTab.click();
      await page.waitForTimeout(1000);

      // Table should have header cells
      await expect(page.getByText('Key').first()).toBeVisible();
      await expect(page.getByText('Accesses').first()).toBeVisible();

      // Table should have data rows
      const tableRows = page.locator('table tbody tr');
      const rowCount = await tableRows.count();
      expect(rowCount, 'Cache line table should have data rows').toBeGreaterThan(0);
    }

    assertClean(consoleErrors, uncaughtErrors);
  });

  test('MESI state machine SVG renders with state circles', async ({ page }) => {
    const { consoleErrors, uncaughtErrors } = setupListeners(page);
    await page.goto('./cache');

    await expect(page.getByText('Hit Rate').first()).toBeVisible({ timeout: 15_000 });

    // Switch to MESI Protocol tab
    const mesiTab = page.getByText('MESI Protocol', { exact: true }).first();
    if (await mesiTab.isVisible().catch(() => false)) {
      await mesiTab.click();
      await page.waitForTimeout(1000);

      // State machine diagram should render
      await expect(page.getByText('MESI State Machine').first()).toBeVisible();
      const circles = page.locator('svg circle');
      const circleCount = await circles.count();
      expect(circleCount, 'MESI state machine should render state circles').toBeGreaterThan(0);
    }

    assertClean(consoleErrors, uncaughtErrors);
  });

  test('eviction eulogies feed populates with memorial entries', async ({ page }) => {
    const { consoleErrors, uncaughtErrors } = setupListeners(page);
    await page.goto('./cache');

    await expect(page.getByText('Hit Rate').first()).toBeVisible({ timeout: 15_000 });

    // Switch to Eulogies tab
    const eulogyTab = page.getByText('Eulogies', { exact: true }).first();
    if (await eulogyTab.isVisible().catch(() => false)) {
      await eulogyTab.click();
      await page.waitForTimeout(1000);

      // Eulogies should contain "In Memoriam" text
      await expect(page.getByText('In Memoriam').first()).toBeVisible({ timeout: 5000 });
    }

    assertClean(consoleErrors, uncaughtErrors);
  });
});

// ---------------------------------------------------------------------------
// Compliance Center Data Flow
// ---------------------------------------------------------------------------

test.describe('Compliance Center data flow', () => {
  test('compliance frameworks render with score gauges', async ({ page }) => {
    const { consoleErrors, uncaughtErrors } = setupListeners(page);
    await page.goto('./compliance');

    await expect(page.getByText('Compliance Findings').first()).toBeVisible({ timeout: 15_000 });

    // Framework cards should be present
    for (const fw of ['SOX', 'GDPR', 'HIPAA']) {
      await expect(page.getByText(fw).first()).toBeVisible();
    }

    // Score gauge SVG should render
    const gauges = page.locator('main svg');
    const gaugeCount = await gauges.count();
    expect(gaugeCount, 'Compliance gauges should render').toBeGreaterThan(0);

    assertClean(consoleErrors, uncaughtErrors);
  });

  test('findings table populates with data rows', async ({ page }) => {
    const { consoleErrors, uncaughtErrors } = setupListeners(page);
    await page.goto('./compliance');

    await expect(page.getByText('Compliance Findings').first()).toBeVisible({ timeout: 15_000 });

    // The findings table should have header columns
    await expect(page.getByText('Severity').first()).toBeVisible();
    await expect(page.getByText('Framework').first()).toBeVisible();

    // Table should have data rows
    const rows = page.locator('table tbody tr');
    const rowCount = await rows.count();
    expect(rowCount, 'Findings table should have data rows').toBeGreaterThan(0);

    assertClean(consoleErrors, uncaughtErrors);
  });
});

// ---------------------------------------------------------------------------
// Blockchain Explorer Data Flow
// ---------------------------------------------------------------------------

test.describe('Blockchain Explorer data flow', () => {
  test('chain visualization renders block elements', async ({ page }) => {
    const { consoleErrors, uncaughtErrors } = setupListeners(page);
    await page.goto('./blockchain');

    await expect(page.getByText('Chain Visualization').first()).toBeVisible({ timeout: 15_000 });

    // Stats bar should have numeric values (rendered once stats load)
    await expect(page.getByText('Block Height').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('Total Transactions').first()).toBeVisible();

    // Block elements render asynchronously after fetchBlocks resolves.
    // Wait for at least one block to appear in the chain strip.
    const blocks = page.locator('[id^="block-"]');
    await expect(blocks.first()).toBeAttached({ timeout: 10_000 });
    const blockCount = await blocks.count();
    expect(blockCount, 'Blockchain should render block elements').toBeGreaterThan(0);

    assertClean(consoleErrors, uncaughtErrors);
  });

  test('clicking a block opens the detail panel', async ({ page }) => {
    const { consoleErrors, uncaughtErrors } = setupListeners(page);
    await page.goto('./blockchain');

    await expect(page.getByText('Chain Visualization').first()).toBeVisible({ timeout: 15_000 });

    // Wait for blocks to render asynchronously
    const firstBlock = page.locator('[id^="block-"]').first();
    await expect(firstBlock).toBeAttached({ timeout: 10_000 });

    // Click the first block in the chain
    if (await firstBlock.isVisible().catch(() => false)) {
      await firstBlock.click();
      await page.waitForTimeout(1000);

      // Block detail should show hash and metadata
      await expect(page.getByText('Block #').first()).toBeVisible({ timeout: 5000 });
    }

    assertClean(consoleErrors, uncaughtErrors);
  });
});

// ---------------------------------------------------------------------------
// Evaluation Console Data Flow
// ---------------------------------------------------------------------------

test.describe('Evaluation Console data flow', () => {
  test('evaluation produces results grid with classification cells', async ({ page }) => {
    const { consoleErrors, uncaughtErrors } = setupListeners(page);
    await page.goto('./evaluate');

    await expect(page.getByText('Evaluation Parameters').first()).toBeVisible({ timeout: 10_000 });

    // Set a small range for fast execution
    await page.getByLabel('Range Start').fill('1');
    await page.getByLabel('Range End').fill('20');

    // Execute
    await page.getByRole('button', { name: 'Execute Evaluation' }).click();

    // Results should appear
    await expect(page.getByText('Evaluation Results')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/\d+ evaluations/)).toBeVisible();

    // Session metadata should populate
    await expect(page.getByText('Session ID')).toBeVisible();
    await expect(page.getByText('Total Processing Time')).toBeVisible();

    // Output format viewer should render
    await expect(page.getByText('Output Format Viewer')).toBeVisible();

    assertClean(consoleErrors, uncaughtErrors);
  });

  test('output format tabs switch content between Plain/JSON/XML/CSV', async ({ page }) => {
    const { consoleErrors, uncaughtErrors } = setupListeners(page);
    await page.goto('./evaluate');

    await page.getByLabel('Range Start').fill('1');
    await page.getByLabel('Range End').fill('10');
    await page.getByRole('button', { name: 'Execute Evaluation' }).click();

    await expect(page.getByText('Output Format Viewer')).toBeVisible({ timeout: 15_000 });

    // Cycle through each format tab and verify content renders
    for (const format of ['JSON', 'XML', 'CSV', 'Plain']) {
      const tab = page.getByText(format, { exact: true }).first();
      if (await tab.isVisible().catch(() => false)) {
        await tab.click();
        await page.waitForTimeout(500);

        // The pre element should contain output text
        const pre = page.locator('main pre').first();
        const content = await pre.textContent().catch(() => '');
        expect(
          (content ?? '').length,
          `${format} output should contain formatted evaluation results`,
        ).toBeGreaterThan(0);
      }
    }

    assertClean(consoleErrors, uncaughtErrors);
  });
});
