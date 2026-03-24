import type { Page } from '@playwright/test';
import { expect } from '@playwright/test';

/**
 * Registers a console error listener on the given Playwright Page. Returns an
 * array that accumulates every `console.error` message text during the page
 * lifetime. Call {@link assertNoConsoleErrors} at the end of the test to fail
 * on genuine errors.
 */
export function trackConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      errors.push(msg.text());
    }
  });
  return errors;
}

/**
 * Filters out benign console errors (favicon, manifest, dev-mode HMR noise)
 * and asserts that no genuine errors remain.
 */
export function assertNoConsoleErrors(errors: string[]): void {
  const real = errors.filter(
    (e) =>
      !e.includes('favicon') &&
      !e.includes('manifest') &&
      !e.includes('Obsidian') &&
      !e.includes('HMR') &&
      !e.includes('[Fast Refresh]') &&
      !e.includes('DevTools') &&
      !e.includes('hydration') &&
      !e.includes('Hydration') &&
      !e.includes('hydrated') &&
      !e.includes('404 (Not Found)') &&
      !e.includes('react.dev/link') &&
      !e.includes('server rendered HTML'),
  );
  expect(real).toHaveLength(0);
}
