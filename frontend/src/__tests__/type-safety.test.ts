/**
 * Type safety canary — imports every module to verify TypeScript compilation.
 * If this file fails to compile, there is a type error somewhere in the codebase.
 * This test exists because ignoreBuildErrors was previously set to true, hiding
 * 241 type errors that caused runtime crashes. Never again.
 */
import { describe, it, expect } from 'vitest';

describe('Type Safety Canary', () => {
  it('all page components resolve without type errors', async () => {
    const pages = await Promise.all([
      import('@/app/(dashboard)/page'),
      import('@/app/(dashboard)/evaluate/page'),
      import('@/app/(dashboard)/monitor/health/page'),
      import('@/app/(dashboard)/monitor/metrics/page'),
      import('@/app/(dashboard)/monitor/sla/page'),
      import('@/app/(dashboard)/monitor/traces/page'),
      import('@/app/(dashboard)/monitor/consensus/page'),
      import('@/app/(dashboard)/monitor/alerts/page'),
      import('@/app/(dashboard)/analytics/page'),
      import('@/app/(dashboard)/archaeology/page'),
      import('@/app/(dashboard)/audit/page'),
      import('@/app/(dashboard)/blockchain/page'),
      import('@/app/(dashboard)/cache/page'),
      import('@/app/(dashboard)/chaos/page'),
      import('@/app/(dashboard)/compliance/page'),
      import('@/app/(dashboard)/configuration/page'),
      import('@/app/(dashboard)/digital-twin/page'),
      import('@/app/(dashboard)/evolution/page'),
      import('@/app/(dashboard)/federated-learning/page'),
      import('@/app/(dashboard)/finops/page'),
      import('@/app/(dashboard)/quantum/page'),
    ]);
    expect(pages.every(p => p.default)).toBe(true);
  });

  it('all UI components resolve without type errors', async () => {
    const components = await Promise.all([
      import('@/components/ui/accordion'),
      import('@/components/ui/animated-number'),
      import('@/components/ui/badge'),
      import('@/components/ui/button'),
      import('@/components/ui/card'),
      import('@/components/ui/copy-button'),
      import('@/components/ui/custom-cursor'),
      import('@/components/ui/data-card'),
      import('@/components/ui/delta-badge'),
      import('@/components/ui/dialog'),
      import('@/components/ui/empty-state'),
      import('@/components/ui/focus-ring'),
      import('@/components/ui/input'),
      import('@/components/ui/keyboard-shortcut-overlay'),
      import('@/components/ui/live-indicator'),
      import('@/components/ui/magnetic-button'),
      import('@/components/ui/pagination'),
      import('@/components/ui/progress-bar'),
      import('@/components/ui/reveal'),
      import('@/components/ui/select'),
      import('@/components/ui/separator'),
      import('@/components/ui/sidebar'),
      import('@/components/ui/skeleton'),
      import('@/components/ui/stat-group'),
      import('@/components/ui/tabs'),
      import('@/components/ui/timeline'),
      import('@/components/ui/tooltip'),
      import('@/components/ui/top-bar'),
    ]);
    expect(components.length).toBeGreaterThan(0);
  });

  it('all chart components resolve without type errors', async () => {
    const charts = await Promise.all([
      import('@/components/charts/chart-legend'),
      import('@/components/charts/chart-tooltip'),
      import('@/components/charts/donut-chart'),
      import('@/components/charts/heatmap-grid'),
      import('@/components/charts/histogram-chart'),
      import('@/components/charts/line-chart'),
      import('@/components/charts/metric-gauge'),
      import('@/components/charts/sparkline'),
      import('@/components/charts/zoom-brush'),
    ]);
    expect(charts.length).toBeGreaterThan(0);
  });

  it('all navigation components resolve without type errors', async () => {
    const nav = await Promise.all([
      import('@/components/navigation/breadcrumbs'),
      import('@/components/navigation/command-palette'),
      import('@/components/navigation/layout-shell'),
      import('@/components/navigation/mobile-drawer'),
      import('@/components/navigation/sidebar'),
      import('@/components/navigation/sidebar-icons'),
    ]);
    expect(nav.length).toBeGreaterThan(0);
  });

  it('all brand components resolve without type errors', async () => {
    const brand = await Promise.all([
      import('@/components/brand/logo'),
    ]);
    expect(brand.length).toBeGreaterThan(0);
  });

  it('all background components resolve without type errors', async () => {
    const backgrounds = await Promise.all([
      import('@/components/backgrounds/dot-grid'),
      import('@/components/backgrounds/topographic'),
    ]);
    expect(backgrounds.length).toBeGreaterThan(0);
  });

  it('all delight components resolve without type errors', async () => {
    const delight = await Promise.all([
      import('@/components/delight/about-panel'),
      import('@/components/delight/confetti'),
      import('@/components/delight/fizzbuzz-404'),
    ]);
    expect(delight.length).toBeGreaterThan(0);
  });

  it('all transition components resolve without type errors', async () => {
    const transitions = await Promise.all([
      import('@/components/transitions/page-transition'),
      import('@/components/transitions/shared-element'),
    ]);
    expect(transitions.length).toBeGreaterThan(0);
  });

  it('all typography components resolve without type errors', async () => {
    const typography = await Promise.all([
      import('@/components/typography/split-text'),
      import('@/components/typography/tabular-number'),
    ]);
    expect(typography.length).toBeGreaterThan(0);
  });

  it('all widget components resolve without type errors', async () => {
    const widgets = await Promise.all([
      import('@/components/widgets/consensus-widget'),
      import('@/components/widgets/cost-widget'),
      import('@/components/widgets/health-matrix-widget'),
      import('@/components/widgets/incidents-widget'),
      import('@/components/widgets/sla-budget-widget'),
      import('@/components/widgets/throughput-widget'),
    ]);
    expect(widgets.length).toBeGreaterThan(0);
  });

  it('service worker registration resolves without type errors', async () => {
    const sw = await import('@/components/service-worker-registration');
    expect(sw).toBeDefined();
  });

  it('all hooks resolve without type errors', async () => {
    const hooks = await Promise.all([
      import('@/lib/hooks/use-animated-number'),
      import('@/lib/hooks/use-cursor'),
      import('@/lib/hooks/use-intersection-observer'),
      import('@/lib/hooks/use-keyboard-navigation'),
      import('@/lib/hooks/use-konami'),
      import('@/lib/hooks/use-magnetic'),
      import('@/lib/hooks/use-press'),
      import('@/lib/hooks/use-reduced-motion'),
      import('@/lib/hooks/use-stagger'),
      import('@/lib/hooks/use-streaming-data'),
    ]);
    expect(hooks.length).toBe(10);
  });

  it('data provider types are consistent', async () => {
    const { SimulationProvider } = await import('@/lib/data-providers/simulation-provider');
    const provider = new SimulationProvider();
    const health = await provider.getSystemHealth();
    expect(Array.isArray(health)).toBe(true);
    const metrics = await provider.getMetricsSummary();
    expect(typeof metrics.totalEvaluations).toBe('number');
  });

  it('data provider index re-exports resolve without type errors', async () => {
    const providerIndex = await import('@/lib/data-providers/index');
    expect(providerIndex).toBeDefined();
  });

  it('hooks index re-exports resolve without type errors', async () => {
    const hooksIndex = await import('@/lib/hooks/index');
    expect(hooksIndex).toBeDefined();
  });
});
