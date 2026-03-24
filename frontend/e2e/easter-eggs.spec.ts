import { test, expect } from '@playwright/test';
import { trackConsoleErrors, assertNoConsoleErrors } from './helpers';

/**
 * Enterprise FizzBuzz Platform — Easter Egg E2E Verification
 *
 * Validates the platform's hidden interaction sequences: the Konami code
 * confetti burst, the logo quintuple-click about panel, and the 404
 * resource location failure interface with its ambient FizzBuzz sequence.
 */

let consoleErrors: string[] = [];

test.beforeEach(async ({ page }) => {
  consoleErrors = trackConsoleErrors(page);
});

test.afterEach(() => {
  assertNoConsoleErrors(consoleErrors);
});

test.describe('Konami Code', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('./');
    await page.waitForLoadState('networkidle');
    // Clear any previous Konami activation from localStorage
    await page.evaluate(() => localStorage.removeItem('efp-konami-activated'));
  });

  test('entering the full Konami sequence triggers confetti particles', async ({ page }) => {
    const sequence = [
      'ArrowUp', 'ArrowUp',
      'ArrowDown', 'ArrowDown',
      'ArrowLeft', 'ArrowRight',
      'ArrowLeft', 'ArrowRight',
      'KeyB', 'KeyA',
    ];

    for (const key of sequence) {
      await page.keyboard.press(key);
      await page.waitForTimeout(50);
    }

    // Confetti renders as a fixed overlay with 50 particle spans
    await page.waitForTimeout(500);
    const confettiContainer = page.locator('.fixed.pointer-events-none.overflow-hidden').first();
    const particleCount = await confettiContainer.locator('span').count();
    expect(particleCount).toBeGreaterThanOrEqual(10);
  });

  test('confetti particles self-clean after animation completes', async ({ page }) => {
    const sequence = [
      'ArrowUp', 'ArrowUp',
      'ArrowDown', 'ArrowDown',
      'ArrowLeft', 'ArrowRight',
      'ArrowLeft', 'ArrowRight',
      'KeyB', 'KeyA',
    ];

    for (const key of sequence) {
      await page.keyboard.press(key);
      await page.waitForTimeout(50);
    }

    // Wait for the 1.5s cleanup timeout
    await page.waitForTimeout(2000);
    const confettiParticles = page.locator('.fixed.pointer-events-none.overflow-hidden span');
    const count = await confettiParticles.count();
    expect(count).toBe(0);
  });

  test('Konami activation state persists in localStorage', async ({ page }) => {
    const sequence = [
      'ArrowUp', 'ArrowUp',
      'ArrowDown', 'ArrowDown',
      'ArrowLeft', 'ArrowRight',
      'ArrowLeft', 'ArrowRight',
      'KeyB', 'KeyA',
    ];

    for (const key of sequence) {
      await page.keyboard.press(key);
      await page.waitForTimeout(50);
    }

    await page.waitForTimeout(500);
    const stored = await page.evaluate(() => localStorage.getItem('efp-konami-activated'));
    expect(stored).toBe('true');
  });

  test('incomplete Konami sequence does not trigger confetti', async ({ page }) => {
    // Only enter first 8 keys (missing B, A)
    const partial = [
      'ArrowUp', 'ArrowUp',
      'ArrowDown', 'ArrowDown',
      'ArrowLeft', 'ArrowRight',
      'ArrowLeft', 'ArrowRight',
    ];

    for (const key of partial) {
      await page.keyboard.press(key);
      await page.waitForTimeout(50);
    }

    await page.waitForTimeout(500);
    const stored = await page.evaluate(() => localStorage.getItem('efp-konami-activated'));
    expect(stored).toBeNull();
  });
});

test.describe('Logo Easter Egg', () => {
  // The Wordmark is rendered inside a lg:hidden container, so it is only
  // visible on mobile-width viewports. Use a narrow viewport to access it.
  test.use({ viewport: { width: 375, height: 812 } });

  test.beforeEach(async ({ page }) => {
    await page.goto('./');
    await page.waitForLoadState('networkidle');
  });

  test('clicking logo 5 times opens the About panel', async ({ page }) => {
    const wordmark = page.locator('span[role="button"]').filter({ hasText: /Enterprise/ }).first();

    for (let i = 0; i < 5; i++) {
      await wordmark.click();
      await page.waitForTimeout(100);
    }

    const dialog = page.getByRole('dialog', { name: 'About Enterprise FizzBuzz' });
    await expect(dialog).toBeVisible();
  });

  test('About panel displays platform statistics', async ({ page }) => {
    const wordmark = page.locator('span[role="button"]').filter({ hasText: /Enterprise/ }).first();

    for (let i = 0; i < 5; i++) {
      await wordmark.click();
      await page.waitForTimeout(100);
    }

    await page.waitForTimeout(500);

    await expect(page.getByText('Lines of Code').first()).toBeVisible();
    await expect(page.getByText('300,000+').first()).toBeVisible();
    await expect(page.getByText('Infrastructure Modules').first()).toBeVisible();
    await expect(page.getByText('Custom Exceptions').first()).toBeVisible();
  });

  test('About panel credits Bob McFizzington', async ({ page }) => {
    const wordmark = page.locator('span[role="button"]').filter({ hasText: /Enterprise/ }).first();

    for (let i = 0; i < 5; i++) {
      await wordmark.click();
      await page.waitForTimeout(100);
    }

    await page.waitForTimeout(500);
    await expect(page.getByText('Bob McFizzington').first()).toBeVisible();
  });

  test('fewer than 5 clicks does not open About panel', async ({ page }) => {
    const wordmark = page.locator('span[role="button"]').filter({ hasText: /Enterprise/ }).first();

    for (let i = 0; i < 4; i++) {
      await wordmark.click();
      await page.waitForTimeout(100);
    }

    await page.waitForTimeout(500);
    const dialog = page.getByRole('dialog', { name: 'About Enterprise FizzBuzz' });
    await expect(dialog).toBeHidden();
  });
});

test.describe('404 Page', () => {
  test('displays 404 heading for invalid routes', async ({ page }) => {
    await page.goto('./nonexistent-route-fizzbuzz-42');
    await page.waitForLoadState('networkidle');

    const heading = page.locator('h1').first();
    await expect(heading).toContainText('404');
  });

  test('renders the FizzBuzz evaluation sequence', async ({ page }) => {
    await page.goto('./nonexistent-route-fizzbuzz-42');
    await page.waitForLoadState('networkidle');

    await page.waitForTimeout(1000);
    const bodyText = await page.locator('body').textContent();

    // The background sequence contains FizzBuzz evaluation results
    expect(bodyText).toContain('Fizz');
    expect(bodyText).toContain('Buzz');
    expect(bodyText).toContain('FizzBuzz');
  });

  test('displays return link to Operations Center', async ({ page }) => {
    await page.goto('./nonexistent-route-fizzbuzz-42');
    await page.waitForLoadState('networkidle');

    await expect(page.getByText('Return to Operations Center')).toBeVisible();
  });

  test('displays resource resolution failure message', async ({ page }) => {
    await page.goto('./nonexistent-route-fizzbuzz-42');
    await page.waitForLoadState('networkidle');

    await expect(
      page.getByText('The requested resource was not found')
    ).toBeVisible();
  });
});
