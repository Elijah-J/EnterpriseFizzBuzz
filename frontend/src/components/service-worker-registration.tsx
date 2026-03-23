"use client";

import { useEffect } from "react";

/**
 * Registers the platform service worker for offline capability.
 *
 * The Enterprise FizzBuzz Operations Center must remain accessible even
 * during network partitions — operational awareness cannot be interrupted
 * by infrastructure failures. The service worker caches the application
 * shell to ensure the dashboard loads under all network conditions.
 */
export function ServiceWorkerRegistration() {
  useEffect(() => {
    if (typeof window !== "undefined" && "serviceWorker" in navigator) {
      navigator.serviceWorker.register(`${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/sw.js`).catch(() => {
        // Service worker registration failure is non-fatal.
        // The platform continues to operate without offline support.
      });
    }
  }, []);

  return null;
}
