import { test, expect } from '@playwright/test';

/**
 * Diagnostic: tests every known route in the Enterprise FizzBuzz Platform
 * to identify pages that crash, produce console errors, or fail to render.
 *
 * Routes are relative to the Playwright baseURL (http://localhost:3000/EnterpriseFizzBuzz/).
 * Use './' prefix for relative resolution, not '/' which resolves to the host root.
 */
const routes = [
  { path: './', label: '/' },
  { path: './evaluate', label: '/evaluate' },
  { path: './monitor/health', label: '/monitor/health' },
  { path: './monitor/metrics', label: '/monitor/metrics' },
  { path: './monitor/sla', label: '/monitor/sla' },
  { path: './monitor/traces', label: '/monitor/traces' },
  { path: './monitor/alerts', label: '/monitor/alerts' },
  { path: './monitor/consensus', label: '/monitor/consensus' },
  { path: './cache', label: '/cache' },
  { path: './compliance', label: '/compliance' },
  { path: './blockchain', label: '/blockchain' },
  { path: './analytics', label: '/analytics' },
  { path: './configuration', label: '/configuration' },
  { path: './audit', label: '/audit' },
  { path: './chaos', label: '/chaos' },
  { path: './digital-twin', label: '/digital-twin' },
  { path: './finops', label: '/finops' },
  { path: './quantum', label: '/quantum' },
  { path: './evolution', label: '/evolution' },
  { path: './federated-learning', label: '/federated-learning' },
  { path: './archaeology', label: '/archaeology' },
  { path: './nonexistent-route', label: '/nonexistent-route' },
];

for (const { path, label } of routes) {
  test(`Page loads without crash: ${label}`, async ({ page }) => {
    const errors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    page.on('pageerror', err => errors.push(err.message));

    await page.goto(path, { timeout: 15000 });

    // Wait for actual content
    await page.locator('main').waitFor({ state: 'visible', timeout: 10000 });

    // Check for heading
    const h1 = page.locator('h1').first();
    await expect(h1).toBeVisible({ timeout: 10000 });

    // Filter noise (404-related errors are expected on the nonexistent route)
    const real = errors.filter(
      e =>
        !e.includes('favicon') &&
        !e.includes('manifest') &&
        !e.includes('Obsidian') &&
        !e.includes('sw.js') &&
        !(label === '/nonexistent-route' && e.includes('404')),
    );

    expect(real, `Console errors on ${label}: ${real.join(', ')}`).toHaveLength(0);
  });
}
