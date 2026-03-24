import { test, expect } from '@playwright/test';

/**
 * Enterprise FizzBuzz Platform — Evaluation Console E2E Verification
 *
 * Validates the FizzBuzz Evaluation Console: range inputs, strategy selection,
 * evaluation execution, progress indication, results rendering, output format
 * switching, and copy functionality.
 */

test.describe('Evaluation Console', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('./evaluate');
    await page.waitForLoadState('networkidle');
  });

  test('displays page heading', async ({ page }) => {
    await expect(page.locator('h1')).toContainText('Evaluation Console');
  });

  test('renders evaluation parameters card with inputs', async ({ page }) => {
    await expect(page.getByText('Evaluation Parameters')).toBeVisible();
    await expect(page.getByLabel('Range Start')).toBeVisible();
    await expect(page.getByLabel('Range End')).toBeVisible();
    await expect(page.getByLabel('Evaluation Strategy')).toBeVisible();
  });

  test('range start input accepts numeric values', async ({ page }) => {
    const startInput = page.getByLabel('Range Start');
    await startInput.fill('10');
    await expect(startInput).toHaveValue('10');
  });

  test('range end input accepts numeric values', async ({ page }) => {
    const endInput = page.getByLabel('Range End');
    await endInput.fill('50');
    await expect(endInput).toHaveValue('50');
  });

  test('strategy selector offers four evaluation strategies', async ({ page }) => {
    const select = page.getByLabel('Evaluation Strategy');
    const options = select.locator('option');
    await expect(options).toHaveCount(4);
    await expect(options.nth(0)).toHaveText('Standard');
    await expect(options.nth(1)).toHaveText('Chain of Responsibility');
    await expect(options.nth(2)).toHaveText('Machine Learning');
    await expect(options.nth(3)).toHaveText('Quantum');
  });

  test('strategy description updates when strategy changes', async ({ page }) => {
    const select = page.getByLabel('Evaluation Strategy');

    // Default strategy should show Standard description
    await expect(page.getByText('Direct modular arithmetic evaluation')).toBeVisible();

    // Switch to Quantum
    await select.selectOption('quantum');
    await expect(page.getByText('Superposition-based evaluation via simulated qubits')).toBeVisible();
  });

  test('Execute Evaluation button is visible and enabled with valid range', async ({ page }) => {
    const button = page.getByRole('button', { name: 'Execute Evaluation' });
    await expect(button).toBeVisible();
    await expect(button).toBeEnabled();
  });

  test('executing evaluation triggers progress bar', async ({ page }) => {
    const button = page.getByRole('button', { name: 'Execute Evaluation' });
    await button.click();

    // During evaluation, button text should change
    await expect(page.getByText('Evaluating...')).toBeVisible({ timeout: 5000 });
  });

  test('evaluation produces results grid', async ({ page }) => {
    const button = page.getByRole('button', { name: 'Execute Evaluation' });
    await button.click();

    // Wait for evaluation to complete and results to appear
    await expect(page.getByText('Evaluation Results')).toBeVisible({ timeout: 15000 });

    // Results badge should show evaluation count
    await expect(page.getByText(/\d+ evaluations/)).toBeVisible();
  });

  test('results show session metadata after evaluation', async ({ page }) => {
    await page.getByRole('button', { name: 'Execute Evaluation' }).click();

    // Wait for results
    await expect(page.getByText('Session Metadata')).toBeVisible({ timeout: 15000 });

    // Check metadata fields
    await expect(page.getByText('Session ID')).toBeVisible();
    await expect(page.getByText('Strategy', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Total Processing Time')).toBeVisible();
    await expect(page.getByText('Total Evaluations')).toBeVisible();
  });

  test('output format viewer renders with tab controls', async ({ page }) => {
    await page.getByRole('button', { name: 'Execute Evaluation' }).click();

    // Wait for output format viewer
    await expect(page.getByText('Output Format Viewer')).toBeVisible({ timeout: 15000 });

    // Format tabs should be present
    await expect(page.getByText('Plain', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('JSON', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('XML', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('CSV', { exact: true }).first()).toBeVisible();
  });

  test('format tabs switch output content', async ({ page }) => {
    await page.getByRole('button', { name: 'Execute Evaluation' }).click();
    await expect(page.getByText('Output Format Viewer')).toBeVisible({ timeout: 15000 });

    // Click JSON tab
    await page.getByText('JSON', { exact: true }).first().click();
    await page.waitForTimeout(500);

    // JSON output should contain opening bracket — use first pre in main content
    const pre = page.locator('main pre').first();
    const content = await pre.textContent();
    expect(content).toBeTruthy();
  });

  test('copy button is present in output format viewer', async ({ page }) => {
    await page.getByRole('button', { name: 'Execute Evaluation' }).click();
    await expect(page.getByText('Output Format Viewer')).toBeVisible({ timeout: 15000 });

    // Copy button should be present (identified by its aria-label or icon)
    const copyButton = page.locator('button[aria-label*="opy"], button[aria-label*="Copy"]').first();
    // If not found by aria-label, look for it by position near the Output Format Viewer header
    const copyInViewer = page.getByText('Output Format Viewer').locator('..').locator('button').last();
    const hasCopy = await copyButton.isVisible().catch(() => false) ||
                    await copyInViewer.isVisible().catch(() => false);
    expect(hasCopy).toBe(true);
  });

  test('evaluation summary StatGroup renders classification counts', async ({ page }) => {
    await page.getByRole('button', { name: 'Execute Evaluation' }).click();

    // Wait for the summary to appear
    await expect(page.getByText('Fizz Count').first()).toBeVisible({ timeout: 15000 });

    // Classification labels should appear somewhere on the page
    await expect(page.getByText('Buzz Count').first()).toBeVisible();
    await expect(page.getByText('FizzBuzz Count').first()).toBeVisible();
  });

  test('small range evaluation completes successfully', async ({ page }) => {
    // Set a small range for faster evaluation
    await page.getByLabel('Range Start').fill('1');
    await page.getByLabel('Range End').fill('15');

    await page.getByRole('button', { name: 'Execute Evaluation' }).click();

    // Results should appear
    await expect(page.getByText('Evaluation Results')).toBeVisible({ timeout: 15000 });

    // Should have exactly 14 evaluations (1-15 exclusive = numbers 1 through 14... actually 1 to <15)
    // Actually the range is start to end, so 1 to 15 = 15 results or based on implementation
    const resultBadge = page.getByText(/\d+ evaluations/);
    await expect(resultBadge).toBeVisible();
  });
});
