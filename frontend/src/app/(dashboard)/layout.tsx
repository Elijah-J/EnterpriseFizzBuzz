import { DataProvider } from "@/lib/data-providers";

/**
 * Dashboard layout wrapper. Provides the DataProvider context to all
 * pages within the (dashboard) route group, ensuring evaluation
 * services are available without per-page initialization.
 */
export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DataProvider>{children}</DataProvider>;
}
