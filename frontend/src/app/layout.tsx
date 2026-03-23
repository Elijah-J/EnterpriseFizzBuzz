import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
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

export const metadata: Metadata = {
  title: "Enterprise FizzBuzz Operations Center",
  description:
    "Mission-critical monitoring and administration interface for the Enterprise FizzBuzz Platform. Provides real-time observability into FizzBuzz evaluation pipelines, compliance dashboards, and operational analytics.",
  manifest: "/manifest.json",
  themeColor: "#0f172a",
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
      className={`${geistSans.variable} ${geistMono.variable} dark h-full antialiased`}
    >
      <head>
        <meta name="theme-color" content="#0f172a" />
      </head>
      <body className="min-h-full flex bg-panel-950 text-panel-50">
        <ServiceWorkerRegistration />
        {/* Sidebar region */}
        <aside className="hidden lg:flex lg:w-64 lg:flex-col lg:border-r lg:border-panel-700 bg-panel-900">
          <div className="flex h-14 items-center border-b border-panel-700 px-4">
            <span className="text-sm font-semibold tracking-wide text-fizzbuzz-400">
              EFP
            </span>
            <span className="ml-1 text-sm text-panel-400">Operations</span>
          </div>
          <nav className="flex-1 p-4">
            <p className="text-xs text-panel-500 uppercase tracking-wider mb-3">
              Navigation
            </p>
            <ul className="space-y-1 text-sm text-panel-300">
              <li className="rounded px-2 py-1.5 bg-panel-800 text-panel-50">
                Dashboard
              </li>
              <li>
                <Link
                  href="/evaluate"
                  className="block rounded px-2 py-1.5 hover:bg-panel-800 transition-colors"
                >
                  Evaluation Console
                </Link>
              </li>
              <li>
                <Link
                  href="/monitor/health"
                  className="block rounded px-2 py-1.5 hover:bg-panel-800 transition-colors"
                >
                  Infrastructure Monitor
                </Link>
              </li>
            </ul>
            <p className="text-xs text-panel-500 uppercase tracking-wider mb-2 mt-5">
              Monitor
            </p>
            <ul className="space-y-1 text-sm text-panel-300">
              <li>
                <Link
                  href="/monitor/metrics"
                  className="block rounded px-2 py-1.5 hover:bg-panel-800 transition-colors"
                >
                  Metrics
                </Link>
              </li>
              <li>
                <Link
                  href="/monitor/traces"
                  className="block rounded px-2 py-1.5 hover:bg-panel-800 transition-colors"
                >
                  Traces
                </Link>
              </li>
              <li>
                <Link
                  href="/monitor/alerts"
                  className="block rounded px-2 py-1.5 hover:bg-panel-800 transition-colors"
                >
                  Alerts
                </Link>
              </li>
            </ul>
            <p className="text-xs text-panel-500 uppercase tracking-wider mb-2 mt-5">
              Platform
            </p>
            <ul className="space-y-1 text-sm text-panel-300">
              <li>
                <Link
                  href="/compliance"
                  className="block rounded px-2 py-1.5 hover:bg-panel-800 transition-colors"
                >
                  Compliance
                </Link>
              </li>
              <li>
                <Link
                  href="/blockchain"
                  className="block rounded px-2 py-1.5 hover:bg-panel-800 transition-colors"
                >
                  Blockchain
                </Link>
              </li>
              <li>
                <Link
                  href="/analytics"
                  className="block rounded px-2 py-1.5 hover:bg-panel-800 transition-colors"
                >
                  Analytics
                </Link>
              </li>
              <li>
                <Link
                  href="/configuration"
                  className="block rounded px-2 py-1.5 hover:bg-panel-800 transition-colors"
                >
                  Configuration
                </Link>
              </li>
              <li>
                <Link
                  href="/audit"
                  className="block rounded px-2 py-1.5 hover:bg-panel-800 transition-colors"
                >
                  Audit Log
                </Link>
              </li>
            </ul>
          </nav>
        </aside>

        {/* Main content region */}
        <div className="flex flex-1 flex-col">
          {/* Top bar */}
          <header className="flex h-14 items-center justify-between border-b border-panel-700 bg-panel-900 px-6">
            <div className="flex items-center gap-2 text-sm text-panel-400">
              <span>Enterprise FizzBuzz Platform</span>
              <span>/</span>
              <span className="text-panel-50">Dashboard</span>
            </div>
            <div className="flex items-center gap-4">
              <span className="inline-flex items-center gap-1.5 text-xs text-fizz-400">
                <span className="h-2 w-2 rounded-full bg-fizz-400" />
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
