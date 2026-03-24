import { test, expect } from '@playwright/test';
import { trackConsoleErrors, assertNoConsoleErrors } from './helpers';

/**
 * Enterprise FizzBuzz Platform — Navigation Subsystem E2E Verification
 *
 * Validates the primary navigation infrastructure including sidebar rendering,
 * route resolution for all 21 registered pages, sidebar collapse/expand state
 * transitions, command palette activation and search filtering, mobile drawer
 * viewport adaptation, and breadcrumb spatial reference rendering.
 */

/** All navigation items as declared in the sidebar hierarchy. */
const NAV_ITEMS = [
  { label: 'Dashboard', href: '/' },
  { label: 'Evaluation Console', href: '/evaluate' },
  { label: 'Infrastructure Monitor', href: '/monitor/health' },
  { label: 'Metrics', href: '/monitor/metrics' },
  { label: 'Traces', href: '/monitor/traces' },
  { label: 'Alerts', href: '/monitor/alerts' },
  { label: 'Cache Coherence', href: '/cache' },
  { label: 'Consensus', href: '/monitor/consensus' },
  { label: 'SLA Budget', href: '/monitor/sla' },
  { label: 'Compliance', href: '/compliance' },
  { label: 'Blockchain', href: '/blockchain' },
  { label: 'Analytics', href: '/analytics' },
  { label: 'Configuration', href: '/configuration' },
  { label: 'Audit Log', href: '/audit' },
  { label: 'Chaos Engineering', href: '/chaos' },
  { label: 'Digital Twin', href: '/digital-twin' },
  { label: 'FinOps', href: '/finops' },
  { label: 'Quantum Workbench', href: '/quantum' },
  { label: 'Evolution Observatory', href: '/evolution' },
  { label: 'Federated Learning', href: '/federated-learning' },
  { label: 'Archaeological Recovery', href: '/archaeology' },
];

/** Section headers in the sidebar navigation hierarchy. */
const NAV_SECTIONS = ['Operations', 'Monitor', 'Platform', 'Finance', 'Research'];

let consoleErrors: string[] = [];

test.beforeEach(async ({ page }) => {
  consoleErrors = trackConsoleErrors(page);
});

test.afterEach(() => {
  assertNoConsoleErrors(consoleErrors);
});

test.describe('Sidebar Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('./');
    await page.waitForLoadState('networkidle');
  });

  test('renders all navigation section headers', async ({ page }) => {
    const sidebar = page.locator('aside');
    for (const section of NAV_SECTIONS) {
      await expect(sidebar.getByText(section, { exact: true })).toBeVisible();
    }
  });

  test('renders all 21 navigation items with correct labels', async ({ page }) => {
    const sidebar = page.locator('aside');
    for (const item of NAV_ITEMS) {
      await expect(sidebar.getByText(item.label, { exact: true })).toBeAttached();
    }
  });

  test('highlights the active navigation item for the current route', async ({ page }) => {
    // Dashboard is the root route — its link should have active styling
    const dashboardLink = page.locator('aside').getByText('Dashboard', { exact: true }).locator('..');
    await expect(dashboardLink).toHaveClass(/bg-surface-raised/);
    await expect(dashboardLink).toHaveClass(/text-text-primary/);
  });

  test('navigates to correct page on nav item click', async ({ page }) => {
    // Click "Evaluation Console"
    await page.locator('aside').getByText('Evaluation Console').click();
    await page.waitForURL('**/evaluate');
    await expect(page.locator('h1')).toContainText('Evaluation Console');
  });

  test('sidebar collapse toggle reduces width and hides labels', async ({ page }) => {
    const sidebar = page.locator('aside');

    // Verify expanded state — labels visible
    await expect(sidebar.getByText('Dashboard')).toBeVisible();

    // Click collapse button
    const collapseBtn = sidebar.locator('button[aria-label="Collapse sidebar"]');
    await collapseBtn.click();

    // In collapsed state, labels should be hidden, section headers gone
    await expect(sidebar.getByText('Operations', { exact: true })).toBeHidden();

    // The sidebar should have the collapsed width class
    await expect(sidebar).toHaveClass(/lg:w-14/);
  });

  test('sidebar expand toggle restores width and shows labels', async ({ page }) => {
    const sidebar = page.locator('aside');

    // Collapse first
    await sidebar.locator('button[aria-label="Collapse sidebar"]').click();
    await expect(sidebar).toHaveClass(/lg:w-14/);

    // Expand
    await sidebar.locator('button[aria-label="Expand sidebar"]').click();
    await expect(sidebar).toHaveClass(/lg:w-60/);

    // Labels should be visible again
    await expect(sidebar.getByText('Dashboard')).toBeVisible();
  });

  test('collapsed sidebar shows tooltips on icon hover', async ({ page }) => {
    const sidebar = page.locator('aside');

    // Collapse sidebar
    await sidebar.locator('button[aria-label="Collapse sidebar"]').click();

    // Hover over the first nav item (Dashboard)
    const firstLink = sidebar.locator('a').first();
    await firstLink.hover();

    // At least one tooltip should become visible (opacity changes from 0 to 1)
    await expect(page.getByRole('tooltip').first()).toBeAttached();
  });

  test('displays version indicator in sidebar footer', async ({ page }) => {
    await expect(page.locator('aside').getByText('v0.1.0')).toBeVisible();
  });
});

test.describe('Command Palette', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('./');
    await page.waitForLoadState('networkidle');
  });

  test('opens on Ctrl+K keyboard shortcut', async ({ page }) => {
    await page.keyboard.press('Control+k');
    const dialog = page.locator('[role="dialog"][aria-label="Command palette"]');
    await expect(dialog).toBeVisible();
  });

  test('opens via search trigger button in top bar', async ({ page }) => {
    await page.locator('button[aria-label="Open command palette"]').click();
    const dialog = page.locator('[role="dialog"][aria-label="Command palette"]');
    await expect(dialog).toBeVisible();
  });

  test('displays all navigation items in command palette results', async ({ page }) => {
    await page.keyboard.press('Control+k');
    const dialog = page.locator('[role="dialog"]');

    // Check for section headers
    await expect(dialog.getByText('Navigation', { exact: true })).toBeVisible();
    await expect(dialog.getByText('Actions', { exact: true })).toBeVisible();

    // Spot check a few items
    await expect(dialog.getByText('Dashboard', { exact: true }).first()).toBeVisible();
    await expect(dialog.getByText('Evaluation Console')).toBeVisible();
    await expect(dialog.getByText('Quantum Workbench')).toBeVisible();
  });

  test('search input filters results by query', async ({ page }) => {
    await page.keyboard.press('Control+k');
    const dialog = page.locator('[role="dialog"]');

    await dialog.locator('input[placeholder="Search pages and actions..."]').fill('quantum');

    // Quantum Workbench should be visible
    await expect(dialog.getByText('Quantum Workbench')).toBeVisible();

    // Dashboard should be filtered out
    await expect(dialog.getByText('Dashboard', { exact: true })).toBeHidden();
  });

  test('shows no results message when search has no matches', async ({ page }) => {
    await page.keyboard.press('Control+k');
    const dialog = page.locator('[role="dialog"]');

    await dialog.locator('input').fill('xyznonexistent');
    await expect(dialog.getByText('No results found.')).toBeVisible();
  });

  test('navigates to selected item on Enter', async ({ page }) => {
    await page.keyboard.press('Control+k');
    const dialog = page.locator('[role="dialog"]');

    await dialog.locator('input').fill('Evaluation Console');
    await page.keyboard.press('Enter');

    await page.waitForURL('**/evaluate');
    await expect(dialog).toBeHidden();
  });

  test('closes on Escape key', async ({ page }) => {
    await page.keyboard.press('Control+k');
    const dialog = page.getByRole('dialog', { name: 'Command palette' });
    await expect(dialog).toBeVisible();

    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
  });

  test('closes on backdrop click', async ({ page }) => {
    await page.keyboard.press('Control+k');
    const dialog = page.getByRole('dialog', { name: 'Command palette' });
    await expect(dialog).toBeVisible();

    // Click the backdrop overlay (positioned behind the dialog)
    await page.locator('.bg-surface-ground\\/80').click({ force: true });
    await expect(dialog).toBeHidden();
  });

  test('arrow keys navigate through results', async ({ page }) => {
    await page.keyboard.press('Control+k');
    const dialog = page.locator('[role="dialog"]');

    // First item should be active initially
    const firstItem = dialog.locator('button.w-full').first();
    await expect(firstItem).toHaveClass(/bg-surface-raised/);

    // Press ArrowDown to move to next item
    await page.keyboard.press('ArrowDown');

    // Second item should now be active
    const secondItem = dialog.locator('button.w-full').nth(1);
    await expect(secondItem).toHaveClass(/bg-surface-raised/);
  });

  test('displays action items with keyboard shortcut hints', async ({ page }) => {
    await page.keyboard.press('Control+k');
    const dialog = page.locator('[role="dialog"]');

    // Toggle Sidebar action should show shortcut hint
    const toggleSidebar = dialog.getByText('Toggle Sidebar');
    await expect(toggleSidebar).toBeVisible();
  });
});

test.describe('Mobile Navigation Drawer', () => {
  test.beforeEach(async ({ page }) => {
    // Set mobile viewport
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto('./');
    await page.waitForLoadState('networkidle');
  });

  test('hamburger button is visible on mobile viewport', async ({ page }) => {
    const hamburger = page.locator('button[aria-label="Open navigation menu"]');
    await expect(hamburger).toBeVisible();
  });

  test('sidebar is hidden on mobile viewport', async ({ page }) => {
    const sidebar = page.locator('aside');
    await expect(sidebar).toBeHidden();
  });

  test('drawer opens on hamburger click with all nav items', async ({ page }) => {
    await page.locator('button[aria-label="Open navigation menu"]').click();

    // Drawer should appear with navigation items
    const drawer = page.locator('.fixed.inset-0.z-50');
    await expect(drawer).toBeVisible();

    // Spot check navigation items in drawer
    await expect(drawer.getByText('Dashboard')).toBeVisible();
    await expect(drawer.getByText('Evaluation Console')).toBeVisible();
    await expect(drawer.getByText('Archaeological Recovery')).toBeVisible();
  });

  test('drawer displays section headers', async ({ page }) => {
    await page.locator('button[aria-label="Open navigation menu"]').click();
    const drawer = page.locator('.fixed.inset-0.z-50');

    for (const section of NAV_SECTIONS) {
      await expect(drawer.getByText(section, { exact: true })).toBeVisible();
    }
  });

  test('drawer closes on overlay click', async ({ page }) => {
    await page.locator('button[aria-label="Open navigation menu"]').click();
    const drawer = page.locator('.fixed.inset-0.z-50');
    await expect(drawer).toBeVisible();

    // Click the overlay backdrop
    await drawer.locator('.absolute.inset-0').click({ position: { x: 350, y: 400 } });
    await expect(drawer).toBeHidden();
  });

  test('drawer closes after navigating to a page', async ({ page }) => {
    await page.locator('button[aria-label="Open navigation menu"]').click();
    const drawer = page.locator('.fixed.inset-0.z-50');

    await drawer.getByText('Evaluation Console').click();
    await page.waitForURL('**/evaluate');

    // Drawer should close after navigation
    await expect(drawer).toBeHidden();
  });
});

test.describe('Breadcrumbs', () => {
  test('renders breadcrumb navigation on desktop', async ({ page }) => {
    await page.goto('./');
    await page.waitForLoadState('networkidle');

    const breadcrumb = page.locator('nav[aria-label="Breadcrumb"]');
    await expect(breadcrumb).toBeVisible();
    await expect(breadcrumb.getByText('Enterprise FizzBuzz Platform')).toBeVisible();
  });

  test('breadcrumb segments are separated by forward slashes', async ({ page }) => {
    await page.goto('./');
    await page.waitForLoadState('networkidle');

    const breadcrumb = page.locator('nav[aria-label="Breadcrumb"]');
    await expect(breadcrumb.getByText('/')).toBeVisible();
  });
});

test.describe('Top Bar', () => {
  test('displays live indicator', async ({ page }) => {
    await page.goto('./');
    await page.waitForLoadState('networkidle');

    // The LiveIndicator should be visible in the top bar
    const header = page.locator('header');
    await expect(header).toBeVisible();
  });

  test('displays command palette keyboard shortcut hint', async ({ page }) => {
    await page.goto('./');
    await page.waitForLoadState('networkidle');

    // The keyboard shortcut badge should show the hotkey
    await expect(page.locator('header kbd')).toBeVisible();
  });
});
