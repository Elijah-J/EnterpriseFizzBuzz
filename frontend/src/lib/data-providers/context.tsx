"use client";

import {
  createContext,
  useContext,
  useMemo,
  type ReactNode,
} from "react";
import type { IDataProvider } from "./provider";
import { SimulationProvider } from "./simulation-provider";

const DataProviderContext = createContext<IDataProvider | null>(null);

interface DataProviderProps {
  /** Override the default provider. If omitted, the SimulationProvider is used. */
  provider?: IDataProvider;
  children: ReactNode;
}

/**
 * Provides the active IDataProvider to all descendant components.
 *
 * The platform's data access layer is fully abstract — swapping from
 * local simulation to a production REST backend requires only changing
 * the provider prop on this component. No downstream components need
 * modification, ensuring clean separation between evaluation logic
 * and data transport.
 */
export function DataProvider({ provider, children }: DataProviderProps) {
  const value = useMemo(
    () => provider ?? new SimulationProvider(),
    [provider],
  );

  return (
    <DataProviderContext.Provider value={value}>
      {children}
    </DataProviderContext.Provider>
  );
}

/**
 * Retrieves the current data provider from context.
 * Must be called within a <DataProvider> subtree.
 */
export function useDataProvider(): IDataProvider {
  const provider = useContext(DataProviderContext);
  if (!provider) {
    throw new Error(
      "useDataProvider must be used within a <DataProvider>. " +
        "Ensure the evaluation page is wrapped in the DataProvider context.",
    );
  }
  return provider;
}
