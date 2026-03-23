import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const panels = [
  {
    title: "Evaluation Pipeline",
    description: "Real-time FizzBuzz evaluation throughput and latency metrics",
    status: "operational" as const,
  },
  {
    title: "Compliance Status",
    description: "SOX, GDPR, and HIPAA compliance audit results",
    status: "operational" as const,
  },
  {
    title: "Cache Coherence",
    description: "MESI protocol state distribution across cache nodes",
    status: "operational" as const,
  },
  {
    title: "Blockchain Ledger",
    description: "Immutable FizzBuzz evaluation records and block height",
    status: "warning" as const,
  },
  {
    title: "Neural Network",
    description: "ML model accuracy and training loss for Fizz/Buzz classification",
    status: "operational" as const,
  },
  {
    title: "SLA Monitor",
    description: "Service level agreement compliance and uptime tracking",
    status: "operational" as const,
  },
];

const statusVariant: Record<string, "success" | "warning" | "error" | "info"> = {
  operational: "success",
  degraded: "warning",
  outage: "error",
};

export default function Dashboard() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-panel-50">
          Enterprise FizzBuzz Operations Center
        </h1>
        <p className="mt-1 text-sm text-panel-400">
          Centralized monitoring and administration for mission-critical FizzBuzz
          evaluation infrastructure.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {panels.map((panel) => (
          <Card key={panel.title}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-panel-100">
                  {panel.title}
                </h2>
                <Badge variant={statusVariant[panel.status] ?? "info"}>
                  {panel.status}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-panel-400">{panel.description}</p>
              <div className="mt-4 h-24 rounded border border-panel-700 bg-panel-900 flex items-center justify-center">
                <span className="text-xs text-panel-500">
                  Telemetry data pending
                </span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
