import { test, expect } from '@playwright/test';
import { trackConsoleErrors, assertNoConsoleErrors } from './helpers';

/**
 * Enterprise FizzBuzz Platform — Full Page Load Audit
 *
 * Comprehensive load verification for every registered route in the platform.
 * Each test navigates to a single page, waits for the heading to render, verifies
 * at least one meaningful content element is present, and asserts zero console
 * errors. This suite exists to catch crash-on-load regressions that lighter
 * navigation tests may miss.
 */

/** All routable pages with expected heading pattern. */
const PAGES: {
  name: string;
  route: string;
  heading: RegExp;
}[] = [
  { name: 'Dashboard', route: './', heading: /operations center/i },
  { name: 'Evaluation Console', route: './evaluate', heading: /evaluation console/i },
  { name: 'Infrastructure Monitor — Health', route: './monitor/health', heading: /health/i },
  { name: 'Metrics', route: './monitor/metrics', heading: /metric/i },
  { name: 'SLA Budget', route: './monitor/sla', heading: /sla/i },
  { name: 'Traces', route: './monitor/traces', heading: /trac/i },
  { name: 'Alerts', route: './monitor/alerts', heading: /alert/i },
  { name: 'Consensus', route: './monitor/consensus', heading: /consensus/i },
  { name: 'Cache Coherence', route: './cache', heading: /cache/i },
  { name: 'Compliance', route: './compliance', heading: /compliance/i },
  { name: 'Blockchain', route: './blockchain', heading: /blockchain/i },
  { name: 'Analytics', route: './analytics', heading: /analytics/i },
  { name: 'Configuration', route: './configuration', heading: /configuration/i },
  { name: 'Audit Log', route: './audit', heading: /audit/i },
  { name: 'Chaos Engineering', route: './chaos', heading: /chaos/i },
  { name: 'Digital Twin', route: './digital-twin', heading: /digital twin/i },
  { name: 'FinOps', route: './finops', heading: /finops/i },
  { name: 'Quantum Workbench', route: './quantum', heading: /quantum/i },
  { name: 'Evolution Observatory', route: './evolution', heading: /evolution|genetic algorithm/i },
  { name: 'Federated Learning', route: './federated-learning', heading: /federated/i },
  { name: 'Archaeological Recovery', route: './archaeology', heading: /archaeolog/i },
];

test.describe('full-load-audit', () => {
  let consoleErrors: string[];

  test.beforeEach(async ({ page }) => {
    consoleErrors = trackConsoleErrors(page);
  });

  test.afterEach(() => {
    assertNoConsoleErrors(consoleErrors);
  });

  for (const pg of PAGES) {
    test(`${pg.name} loads without errors`, async ({ page }) => {
      await page.goto(pg.route);

      // Wait for the page-specific heading. Some layouts (monitor sub-routes)
      // render a parent h1 ("Infrastructure Monitor") alongside the page h1.
      // Use getByRole with accessible name matching, which handles both plain
      // text headings and SplitText components (which set aria-label).
      const heading = page.getByRole('heading', { level: 1, name: pg.heading });
      await heading.waitFor({ timeout: 10000 });
      await expect(heading).toBeVisible();

      // Verify meaningful content rendered beyond the heading. The main element
      // must contain at least one child that is not just the h1 — a div, section,
      // table, canvas, svg, or form counts as real content.
      const mainContent = page.locator('main');
      await expect(mainContent).toBeVisible();
      const contentChildren = mainContent.locator('div, section, table, canvas, svg, form, ul, ol, article');
      await expect(contentChildren.first()).toBeAttached({ timeout: 10000 });
    });
  }

  test('404 page loads without errors', async ({ page }) => {
    await page.goto('./nonexistent-page');

    const heading = page.getByRole('heading', { level: 1 });
    await heading.waitFor({ timeout: 10000 });
    await expect(heading).toBeVisible();
    await expect(heading).toContainText('404');
  });
});
