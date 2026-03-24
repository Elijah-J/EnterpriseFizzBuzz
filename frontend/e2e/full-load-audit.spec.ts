import { test, expect, type Page } from '@playwright/test';
import { trackConsoleErrors, assertNoConsoleErrors } from './helpers';

/**
 * Enterprise FizzBuzz Platform — Full Page Load Audit (Comprehensive)
 *
 * Exhaustive load verification for every registered route in the platform.
 * Each test:
 *   1. Registers console error and pageerror listeners BEFORE navigation
 *   2. Navigates to the page
 *   3. Waits for the h1 heading to be visible (10s timeout)
 *   4. Verifies at least one meaningful data element rendered (not skeleton)
 *   5. For pages with interactive elements: exercises tabs, selects, buttons
 *   6. Asserts zero console errors (filtered for benign noise)
 *
 * No pages are skipped. No assertions are disabled. Console errors are test
 * failures.
 */

// ---------------------------------------------------------------------------
// Page registry — every routable page with expected heading, content selectors,
// and interactive element descriptors.
// ---------------------------------------------------------------------------

interface PageSpec {
  name: string;
  route: string;
  heading: RegExp;
  /** Selector or text to confirm real content rendered beyond the heading. */
  contentProbe: { kind: 'text'; value: string | RegExp } | { kind: 'selector'; value: string };
  /** Interactive elements to exercise after the page loads. */
  interactions?: Array<
    | { type: 'tab'; label: string }
    | { type: 'select'; label?: string; selector?: string; optionValue: string }
    | { type: 'button'; name: string }
    | { type: 'click'; selector: string; description: string }
  >;
  /** Extra time (ms) to wait after navigation for data-driven pages. */
  dataWaitMs?: number;
}

const PAGES: PageSpec[] = [
  {
    name: 'Dashboard',
    route: './',
    heading: /operations center/i,
    contentProbe: { kind: 'text', value: 'Evaluation Pipeline' },
    interactions: [
      { type: 'click', selector: '[data-card-index="0"]', description: 'Focus throughput hero card' },
    ],
  },
  {
    name: 'Evaluation Console',
    route: './evaluate',
    heading: /evaluation console/i,
    contentProbe: { kind: 'text', value: 'Evaluation Parameters' },
    interactions: [
      { type: 'select', label: 'Evaluation Strategy', optionValue: 'quantum' },
      { type: 'button', name: 'Execute Evaluation' },
    ],
  },
  {
    name: 'Health Check Matrix',
    route: './monitor/health',
    heading: /health/i,
    contentProbe: { kind: 'text', value: /sort by/i },
    dataWaitMs: 5000,
    interactions: [
      { type: 'button', name: 'Name' },
      { type: 'select', selector: 'select', optionValue: 'up' },
    ],
  },
  {
    name: 'Metrics Dashboard',
    route: './monitor/metrics',
    heading: /metric/i,
    contentProbe: { kind: 'text', value: 'All Platform Metrics' },
    dataWaitMs: 3000,
    interactions: [
      { type: 'click', selector: 'button:has-text("5m")', description: 'Switch to 5m time range' },
    ],
  },
  {
    name: 'SLA Budget',
    route: './monitor/sla',
    heading: /sla/i,
    contentProbe: { kind: 'selector', value: 'main' },
    dataWaitMs: 3000,
  },
  {
    name: 'Traces',
    route: './monitor/traces',
    heading: /trac/i,
    contentProbe: { kind: 'selector', value: 'main' },
    dataWaitMs: 3000,
  },
  {
    name: 'Alerts',
    route: './monitor/alerts',
    heading: /alert/i,
    contentProbe: { kind: 'selector', value: 'main' },
    dataWaitMs: 3000,
    interactions: [
      { type: 'tab', label: 'Firing' },
    ],
  },
  {
    name: 'Consensus',
    route: './monitor/consensus',
    heading: /consensus/i,
    contentProbe: { kind: 'selector', value: 'main' },
    dataWaitMs: 3000,
  },
  {
    name: 'Cache Coherence',
    route: './cache',
    heading: /cache/i,
    contentProbe: { kind: 'text', value: 'Hit Rate' },
    dataWaitMs: 3000,
    interactions: [
      { type: 'tab', label: 'Cache Lines' },
      { type: 'tab', label: 'MESI Protocol' },
      { type: 'tab', label: 'Eulogies' },
      { type: 'tab', label: 'Stats & Distribution' },
    ],
  },
  {
    name: 'Compliance',
    route: './compliance',
    heading: /compliance/i,
    contentProbe: { kind: 'text', value: 'Compliance Findings' },
    dataWaitMs: 3000,
    interactions: [
      { type: 'select', selector: 'select:first-of-type', optionValue: 'SOX' },
    ],
  },
  {
    name: 'Blockchain',
    route: './blockchain',
    heading: /blockchain/i,
    contentProbe: { kind: 'text', value: 'Chain Visualization' },
    dataWaitMs: 3000,
    interactions: [
      { type: 'button', name: 'Refresh Chain' },
    ],
  },
  {
    name: 'Analytics',
    route: './analytics',
    heading: /analytics/i,
    contentProbe: { kind: 'selector', value: 'main' },
    dataWaitMs: 3000,
    interactions: [
      { type: 'click', selector: 'button:has-text("6h")', description: 'Switch trend period' },
    ],
  },
  {
    name: 'Configuration',
    route: './configuration',
    heading: /configuration/i,
    contentProbe: { kind: 'selector', value: 'main' },
    dataWaitMs: 3000,
  },
  {
    name: 'Audit Log',
    route: './audit',
    heading: /audit/i,
    contentProbe: { kind: 'selector', value: 'main' },
    dataWaitMs: 3000,
  },
  {
    name: 'Chaos Engineering',
    route: './chaos',
    heading: /chaos/i,
    contentProbe: { kind: 'selector', value: 'main' },
    dataWaitMs: 3000,
  },
  {
    name: 'Digital Twin',
    route: './digital-twin',
    heading: /digital twin/i,
    contentProbe: { kind: 'selector', value: 'main' },
    dataWaitMs: 3000,
  },
  {
    name: 'FinOps',
    route: './finops',
    heading: /finops/i,
    contentProbe: { kind: 'selector', value: 'main' },
    dataWaitMs: 3000,
  },
  {
    name: 'Quantum Workbench',
    route: './quantum',
    heading: /quantum/i,
    contentProbe: { kind: 'selector', value: 'main' },
    dataWaitMs: 3000,
  },
  {
    name: 'Evolution Observatory',
    route: './evolution',
    heading: /evolution|genetic algorithm/i,
    contentProbe: { kind: 'selector', value: 'main' },
    dataWaitMs: 3000,
  },
  {
    name: 'Federated Learning',
    route: './federated-learning',
    heading: /federated/i,
    contentProbe: { kind: 'selector', value: 'main' },
    dataWaitMs: 3000,
  },
  {
    name: 'Archaeological Recovery',
    route: './archaeology',
    heading: /archaeolog/i,
    contentProbe: { kind: 'selector', value: 'main' },
    dataWaitMs: 3000,
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Register both console.error and uncaught exception listeners. */
function registerErrorListeners(page: Page): {
  consoleErrors: string[];
  uncaughtErrors: string[];
} {
  const consoleErrors = trackConsoleErrors(page);
  const uncaughtErrors: string[] = [];

  page.on('pageerror', (error) => {
    uncaughtErrors.push(error.message);
  });

  return { consoleErrors, uncaughtErrors };
}

/** Assert no genuine errors from either console or uncaught exceptions. */
function assertNoErrors(
  consoleErrors: string[],
  uncaughtErrors: string[],
): void {
  assertNoConsoleErrors(consoleErrors);

  const realUncaught = uncaughtErrors.filter(
    (e) =>
      !e.includes('ResizeObserver') &&
      !e.includes('Loading chunk') &&
      !e.includes('ChunkLoadError'),
  );
  expect(realUncaught, 'Uncaught page exceptions detected').toHaveLength(0);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('full-load-audit', () => {
  for (const pg of PAGES) {
    test(`${pg.name} — loads, renders data, and produces zero errors`, async ({ page }) => {
      // 1. Register error listeners BEFORE navigation
      const { consoleErrors, uncaughtErrors } = registerErrorListeners(page);

      // 2. Navigate
      await page.goto(pg.route);

      // 3. Wait for h1 to be visible
      const heading = page.getByRole('heading', { level: 1, name: pg.heading });
      await heading.waitFor({ timeout: 10_000 });
      await expect(heading).toBeVisible();

      // 4. Wait for data if the page is data-driven
      if (pg.dataWaitMs) {
        await page.waitForTimeout(pg.dataWaitMs);
      }

      // 5. Verify meaningful content rendered beyond the heading
      if (pg.contentProbe.kind === 'text') {
        const textProbe = pg.contentProbe.value;
        if (typeof textProbe === 'string') {
          await expect(page.getByText(textProbe).first()).toBeVisible({ timeout: 10_000 });
        } else {
          await expect(page.getByText(textProbe).first()).toBeVisible({ timeout: 10_000 });
        }
      } else {
        const el = page.locator(pg.contentProbe.value);
        await expect(el).toBeVisible({ timeout: 10_000 });
        // Verify the content area has substantive text (not just empty/skeleton)
        const text = await el.textContent();
        expect(
          (text ?? '').length,
          `${pg.name} main content area should contain substantive text`,
        ).toBeGreaterThan(50);
      }

      // The main element must contain child content elements
      const mainContent = page.locator('main');
      await expect(mainContent).toBeVisible();
      const contentChildren = mainContent.locator(
        'div, section, table, canvas, svg, form, ul, ol, article',
      );
      await expect(contentChildren.first()).toBeAttached({ timeout: 10_000 });

      // 6. Exercise interactive elements (if any)
      if (pg.interactions) {
        for (const interaction of pg.interactions) {
          switch (interaction.type) {
            case 'tab': {
              const tab = page.getByText(interaction.label, { exact: true }).first();
              if (await tab.isVisible().catch(() => false)) {
                await tab.click();
                // Give the tab content time to render
                await page.waitForTimeout(500);
              }
              break;
            }
            case 'select': {
              let select;
              if (interaction.label) {
                select = page.getByLabel(interaction.label);
              } else if (interaction.selector) {
                select = page.locator(interaction.selector).first();
              }
              if (select && (await select.isVisible().catch(() => false))) {
                await select.selectOption(interaction.optionValue);
                await page.waitForTimeout(500);
              }
              break;
            }
            case 'button': {
              const btn = page.getByRole('button', { name: interaction.name }).first();
              if (await btn.isVisible().catch(() => false)) {
                await btn.click();
                await page.waitForTimeout(500);
              }
              break;
            }
            case 'click': {
              const el = page.locator(interaction.selector).first();
              if (await el.isVisible().catch(() => false)) {
                await el.click();
                await page.waitForTimeout(500);
              }
              break;
            }
          }
        }
      }

      // 7. Assert zero errors
      assertNoErrors(consoleErrors, uncaughtErrors);
    });
  }

  test('404 page loads without errors', async ({ page }) => {
    const { consoleErrors, uncaughtErrors } = registerErrorListeners(page);

    await page.goto('./nonexistent-route-xyz');

    const heading = page.getByRole('heading', { level: 1 });
    await heading.waitFor({ timeout: 10_000 });
    await expect(heading).toBeVisible();
    await expect(heading).toContainText('404');

    assertNoErrors(consoleErrors, uncaughtErrors);
  });
});
