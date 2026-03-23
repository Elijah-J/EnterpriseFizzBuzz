import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { ThroughputWidget } from "@/components/widgets/throughput-widget";
import { HealthMatrixWidget } from "@/components/widgets/health-matrix-widget";
import { SLABudgetWidget } from "@/components/widgets/sla-budget-widget";
import { IncidentsWidget } from "@/components/widgets/incidents-widget";
import { CostWidget } from "@/components/widgets/cost-widget";
import { ConsensusWidget } from "@/components/widgets/consensus-widget";

/**
 * Executive Dashboard — The primary operational view of the Enterprise
 * FizzBuzz Platform. Provides real-time visibility into evaluation
 * throughput, infrastructure health, SLA compliance, incident status,
 * FinOps expenditure, and distributed consensus state.
 *
 * This is a Server Component that composes Client Component widgets.
 * Each widget manages its own polling interval via the DataProvider
 * context, ensuring independent refresh cycles and graceful degradation
 * if any individual telemetry source becomes unavailable.
 */
export default function ExecutiveDashboard() {
  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-panel-50">
          Enterprise FizzBuzz Operations Center
        </h1>
        <p className="mt-1 text-sm text-panel-400">
          Centralized monitoring and administration for mission-critical FizzBuzz
          evaluation infrastructure. All telemetry data refreshes automatically.
        </p>
      </div>

      {/* Widget grid — 3 columns on desktop, 2 on tablet, 1 on mobile */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {/* Throughput — Primary KPI, top-left prominence */}
        <Card>
          <CardHeader>
            <h2 className="text-sm font-semibold text-panel-100">
              Evaluation Pipeline
            </h2>
          </CardHeader>
          <CardContent>
            <ThroughputWidget />
          </CardContent>
        </Card>

        {/* Health Matrix — Spans full width on large screens for density */}
        <Card className="xl:col-span-2">
          <CardHeader>
            <h2 className="text-sm font-semibold text-panel-100">
              Infrastructure Health Matrix
            </h2>
          </CardHeader>
          <CardContent>
            <HealthMatrixWidget />
          </CardContent>
        </Card>

        {/* SLA Budget */}
        <Card>
          <CardHeader>
            <h2 className="text-sm font-semibold text-panel-100">
              SLA Compliance
            </h2>
          </CardHeader>
          <CardContent>
            <SLABudgetWidget />
          </CardContent>
        </Card>

        {/* Incidents */}
        <Card>
          <CardHeader>
            <h2 className="text-sm font-semibold text-panel-100">
              Incident Status
            </h2>
          </CardHeader>
          <CardContent>
            <IncidentsWidget />
          </CardContent>
        </Card>

        {/* Cost */}
        <Card>
          <CardHeader>
            <h2 className="text-sm font-semibold text-panel-100">
              FinOps Expenditure
            </h2>
          </CardHeader>
          <CardContent>
            <CostWidget />
          </CardContent>
        </Card>

        {/* Consensus */}
        <Card>
          <CardHeader>
            <h2 className="text-sm font-semibold text-panel-100">
              Paxos Consensus
            </h2>
          </CardHeader>
          <CardContent>
            <ConsensusWidget />
          </CardContent>
        </Card>

        {/* Placeholder for future widgets */}
        <Card className="xl:col-span-2">
          <CardHeader>
            <h2 className="text-sm font-semibold text-panel-100">
              Blockchain Ledger
            </h2>
          </CardHeader>
          <CardContent>
            <div className="flex h-24 items-center justify-center rounded border border-panel-700 bg-panel-900">
              <span className="text-xs text-panel-500">
                Block explorer integration pending deployment
              </span>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
