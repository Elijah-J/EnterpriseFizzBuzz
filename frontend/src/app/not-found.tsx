import { FizzBuzz404 } from "@/components/delight/fizzbuzz-404";

/**
 * Next.js 404 handler — renders the Resource Location Failure Interface
 * when the routing subsystem cannot resolve a requested path to any
 * registered page component. This file must exist at the app root level
 * for the App Router to serve it as the global not-found page.
 */
export default function NotFound() {
  return <FizzBuzz404 />;
}
