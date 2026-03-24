import type { Metadata } from "next";
import { Geist, Geist_Mono, Instrument_Serif } from "next/font/google";
import { LayoutShell } from "@/components/navigation/layout-shell";
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
        <LayoutShell>{children}</LayoutShell>
      </body>
    </html>
  );
}
