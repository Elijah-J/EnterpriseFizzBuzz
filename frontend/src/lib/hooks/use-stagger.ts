/**
 * Computes staggered delay values for orchestrating sequential entrance
 * animations across a list of child elements. Each child receives a
 * progressively larger delay, creating a cascading reveal effect that
 * communicates hierarchical structure and draws attention through the
 * list in reading order.
 *
 * The stagger pattern is a core component of the platform's motion
 * choreography system: one coordinated entrance sequence per page load,
 * with each element arriving 50ms after its predecessor by default.
 */

interface UseStaggerOptions {
  /** Delay applied to the first child in milliseconds. Default 0. */
  baseDelay?: number;
  /** Delay increment between consecutive children in milliseconds. Default 50. */
  increment?: number;
}

/**
 * Returns an array of delay values (in milliseconds) for `count` children.
 * Each value represents the CSS `animation-delay` or `transition-delay`
 * that should be applied to the corresponding child element.
 */
export function useStagger(
  count: number,
  options: UseStaggerOptions = {},
): number[] {
  const { baseDelay = 0, increment = 50 } = options;

  return Array.from({ length: count }, (_, i) => baseDelay + i * increment);
}
