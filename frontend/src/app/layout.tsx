import type { Metadata } from "next";
import { Geist, Geist_Mono, Instrument_Serif } from "next/font/google";
import Link from "next/link";
import { Wordmark } from "@/components/brand";
import { ServiceWorkerRegistration } from "@/components/service-worker-registration";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const instrumentSerif = Instrument_Serif({
  variable: "--font-serif",
  weight: "400",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Enterprise FizzBuzz Operations Center",
  description:
    "Mission-critical monitoring and administration interface for the Enterprise FizzBuzz Platform. Provides real-time observability into FizzBuzz evaluation pipelines, compliance dashboards, and operational analytics.",
  manifest: "/manifest.json",
  themeColor: "#0C0A09",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "EFB Platform",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${instrumentSerif.variable} dark h-full antialiased`}
    >
      <head>
        <meta name="theme-color" content="#0C0A09" />
      </head>
      <body className="min-h-full flex bg-surface-ground text-text-primary">
        <ServiceWorkerRegistration />
        {/* Sidebar region */}
        <aside className="hidden lg:flex lg:w-64 lg:flex-col lg:border-r lg:border-border-subtle bg-surface-base">
          <div className="flex h-14 items-center border-b border-border-subtle px-4">
            <Wordmark />
          </div>
          <nav className="flex-1 p-4">
            <p className="text-xs text-text-muted uppercase tracking-wider mb-3">
              Navigation
            </p>
            <ul className="space-y-1 text-sm text-text-secondary">
              <li className="rounded px-2 py-1.5 bg-surface-raised text-text-primary">
                Dashboard
              </li>
              <li>
                <Link
                  href="/evaluate"
                  className="block rounded px-2 py-1.5 hover:bg-surface-raised transition-colors"
                >
                  Evaluation Console
                </Link>
              </li>
              <li>
                <Link
                  href="/monitor/health"
                  className="block rounded px-2 py-1.5 hover:bg-surface-raised transition-colors"
                >
                  Infrastructure Monitor
                </Link>
              </li>
            </ul>
            <p className="text-xs text-text-muted uppercase tracking-wider mb-2 mt-5">
              Monitor
            </p>
            <ul className="space-y-1 text-sm text-text-secondary">
              <li>
                <Link
                  href="/monitor/metrics"
                  className="block rounded px-2 py-1.5 hover:bg-surface-raised transition-colors"
                >
                  Metrics
                </Link>
              </li>
              <li>
                <Link
                  href="/monitor/traces"
                  className="block rounded px-2 py-1.5 hover:bg-surface-raised transition-colors"
                >
                  Traces
                </Link>
              </li>
              <li>
                <Link
                  href="/monitor/alerts"
                  className="block rounded px-2 py-1.5 hover:bg-surface-raised transition-colors"
                >
                  Alerts
                </Link>
              </li>
              <li>
                <Link
                  href="/cache"
                  className="block rounded px-2 py-1.5 hover:bg-surface-raised transition-colors"
                >
                  Cache Coherence
                </Link>
              </li>
              <li>
                <Link
                  href="/monitor/consensus"
                  className="block rounded px-2 py-1.5 hover:bg-surface-raised transition-colors"
                >
                  Consensus
                </Link>
              </li>
            </ul>
            <p className="text-xs text-text-muted uppercase tracking-wider mb-2 mt-5">
              Platform
            </p>
            <ul className="space-y-1 text-sm text-text-secondary">
              <li>
                <Link
                  href="/compliance"
                  className="block rounded px-2 py-1.5 hover:bg-surface-raised transition-colors"
                >
                  Compliance
                </Link>
              </li>
              <li>
                <Link
                  href="/blockchain"
                  className="block rounded px-2 py-1.5 hover:bg-surface-raised transition-colors"
                >
                  Blockchain
                </Link>
              </li>
              <li>
                <Link
                  href="/analytics"
                  className="block rounded px-2 py-1.5 hover:bg-surface-raised transition-colors"
                >
                  Analytics
                </Link>
              </li>
              <li>
                <Link
                  href="/configuration"
                  className="block rounded px-2 py-1.5 hover:bg-surface-raised transition-colors"
                >
                  Configuration
                </Link>
              </li>
              <li>
                <Link
                  href="/audit"
                  className="block rounded px-2 py-1.5 hover:bg-surface-raised transition-colors"
                >
                  Audit Log
                </Link>
              </li>
              <li>
                <Link
                  href="/chaos"
                  className="block rounded px-2 py-1.5 hover:bg-surface-raised transition-colors"
                >
                  Chaos Engineering
                </Link>
              </li>
              <li>
                <Link
                  href="/digital-twin"
                  className="block rounded px-2 py-1.5 hover:bg-surface-raised transition-colors"
                >
                  Digital Twin
                </Link>
              </li>
            </ul>
            <p className="text-xs text-text-muted uppercase tracking-wider mb-2 mt-5">
              Finance
            </p>
            <ul className="space-y-1 text-sm text-text-secondary">
              <li>
                <Link
                  href="/finops"
                  className="block rounded px-2 py-1.5 hover:bg-surface-raised transition-colors"
                >
                  FinOps
                </Link>
              </li>
            </ul>
            <p className="text-xs text-text-muted uppercase tracking-wider mb-2 mt-5">
              Research
            </p>
            <ul className="space-y-1 text-sm text-text-secondary">
              <li>
                <Link
                  href="/quantum"
                  className="block rounded px-2 py-1.5 hover:bg-surface-raised transition-colors"
                >
                  Quantum Workbench
                </Link>
              </li>
              <li>
                <Link
                  href="/evolution"
                  className="block rounded px-2 py-1.5 hover:bg-surface-raised transition-colors"
                >
                  Evolution Observatory
                </Link>
              </li>
              <li>
                <Link
                  href="/federated-learning"
                  className="block rounded px-2 py-1.5 hover:bg-surface-raised transition-colors"
                >
                  Federated Learning
                </Link>
              </li>
              <li>
                <Link
                  href="/archaeology"
                  className="block rounded px-2 py-1.5 hover:bg-surface-raised transition-colors"
                >
                  Archaeological Recovery
                </Link>
              </li>
            </ul>
          </nav>
        </aside>

        {/* Main content region */}
        <div className="flex flex-1 flex-col">
          {/* Top bar */}
          <header className="flex h-14 items-center justify-between border-b border-border-subtle bg-surface-base px-6">
            <div className="flex items-center gap-2 text-sm text-text-secondary">
              <span>Enterprise FizzBuzz Platform</span>
              <span className="text-text-muted">/</span>
              <span className="text-text-primary">Dashboard</span>
            </div>
            <div className="flex items-center gap-4">
              <span className="inline-flex items-center gap-1.5 text-xs text-text-secondary">
                <span className="h-2 w-2 rounded-full bg-accent" />
                All Systems Operational
              </span>
            </div>
          </header>

          {/* Page content */}
          <main className="flex-1 overflow-y-auto p-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
