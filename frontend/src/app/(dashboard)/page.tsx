import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Reveal } from "@/components/ui/reveal";
import { SplitText } from "@/components/typography";
import { ConsensusWidget } from "@/components/widgets/consensus-widget";
import { CostWidget } from "@/components/widgets/cost-widget";
import { HealthMatrixWidget } from "@/components/widgets/health-matrix-widget";
import { IncidentsWidget } from "@/components/widgets/incidents-widget";
import { SLABudgetWidget } from "@/components/widgets/sla-budget-widget";
import { ThroughputWidget } from "@/components/widgets/throughput-widget";

/**
 * Executive Dashboard — The primary operational view of the Enterprise
 * FizzBuzz Platform. Provides real-time visibility into evaluation
 * throughput, infrastructure health, SLA compliance, incident status,
 * FinOps expenditure, and distributed consensus state.
 *
 * The asymmetric bento grid layout establishes visual hierarchy through
 * variable card spans: the throughput hero occupies a 2x2 region,
 * the health matrix stretches full width, and secondary metrics
 * fill single cells. This deliberate asymmetry creates editorial
 * rhythm that distinguishes the layout from uniform dashboard grids.
 *
 * This is a Server Component that composes Client Component widgets.
 * Each widget manages its own polling interval via the DataProvider
 * context, ensuring independent refresh cycles and graceful degradation
 * if any individual telemetry source becomes unavailable.
 */
export default function ExecutiveDashboard() {
  return (
    <div className="relative min-h-full">
      {/* Grain overlay — editorial texture on page background */}
      <div className="grain pointer-events-none absolute inset-0 z-0" />

      <div className="relative z-10 space-y-8">
        {/* Hero header */}
        <Reveal>
          <div>
            <h1 className="heading-display text-gradient-amber">
              <SplitText text="Operations Center" staggerMs={20} animation="slide" />
            </h1>
            <p className="mt-2 text-sm text-text-secondary max-w-xl text-balance">
              Centralized monitoring and administration for mission-critical
              FizzBuzz evaluation infrastructure. All telemetry data refreshes
              automatically.
            </p>
          </div>
        </Reveal>

        {/* Asymmetric bento grid */}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3 auto-rows-auto">
          {/* Throughput — Hero card, 2x2 prominence */}
          <Reveal delay={50}>
            <Card
              tabIndex={0}
              data-card-index={0}
              variant="featured"
              className="xl:col-span-2 xl:row-span-2 h-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-surface-ground"
            >
              <CardHeader>
                <h2 className="heading-section">Evaluation Pipeline</h2>
              </CardHeader>
              <CardContent>
                <ThroughputWidget />
              </CardContent>
            </Card>
          </Reveal>

          {/* SLA Budget — Standard cell beside throughput */}
          <Reveal delay={100}>
            <Card
              tabIndex={0}
              data-card-index={1}
              className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-surface-ground"
            >
              <CardHeader>
                <h2 className="heading-section">SLA Compliance</h2>
              </CardHeader>
              <CardContent>
                <SLABudgetWidget />
              </CardContent>
            </Card>
          </Reveal>

          {/* Incidents — Standard cell */}
          <Reveal delay={150}>
            <Card
              tabIndex={0}
              data-card-index={2}
              className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-surface-ground"
            >
              <CardHeader>
                <h2 className="heading-section">Incident Status</h2>
              </CardHeader>
              <CardContent>
                <IncidentsWidget />
              </CardContent>
            </Card>
          </Reveal>

          {/* Health Matrix — Full width span for maximum density */}
          <Reveal delay={200}>
            <Card
              tabIndex={0}
              data-card-index={3}
              className="xl:col-span-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-surface-ground"
            >
              <CardHeader>
                <h2 className="heading-section">
                  Infrastructure Health Matrix
                </h2>
              </CardHeader>
              <CardContent>
                <HealthMatrixWidget />
              </CardContent>
            </Card>
          </Reveal>

          {/* Cost — Standard cell */}
          <Reveal delay={250}>
            <Card
              tabIndex={0}
              data-card-index={4}
              className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-surface-ground"
            >
              <CardHeader>
                <h2 className="heading-section">FinOps Expenditure</h2>
              </CardHeader>
              <CardContent>
                <CostWidget />
              </CardContent>
            </Card>
          </Reveal>

          {/* Consensus — Standard cell */}
          <Reveal delay={300}>
            <Card
              tabIndex={0}
              data-card-index={5}
              className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-surface-ground"
            >
              <CardHeader>
                <h2 className="heading-section">Paxos Consensus</h2>
              </CardHeader>
              <CardContent>
                <ConsensusWidget />
              </CardContent>
            </Card>
          </Reveal>

          {/* Blockchain Ledger — Wide placeholder */}
          <Reveal delay={350}>
            <Card
              tabIndex={0}
              data-card-index={6}
              className="xl:col-span-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-surface-ground"
              variant="elevated"
            >
              <CardHeader>
                <h2 className="heading-section">Blockchain Ledger</h2>
              </CardHeader>
              <CardContent>
                <EmptyState
                  title="Block Explorer"
                  description="Distributed ledger integration is pending deployment. The blockchain subsystem will provide immutable audit trails for all FizzBuzz evaluation records."
                />
              </CardContent>
            </Card>
          </Reveal>
        </div>
      </div>
    </div>
  );
}
