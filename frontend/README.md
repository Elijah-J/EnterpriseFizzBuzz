# Enterprise FizzBuzz Operations Center

Web-based monitoring and administration interface for the Enterprise FizzBuzz Platform (EFP).

## Purpose

The Operations Center provides centralized observability into all FizzBuzz evaluation subsystems, including real-time pipeline metrics, compliance dashboards, cache coherence visualization, blockchain ledger inspection, and SLA monitoring. It is the primary interface through which platform operators manage mission-critical FizzBuzz infrastructure.

## Technology Stack

| Layer | Technology | Justification |
|-------|-----------|---------------|
| Framework | Next.js 15 (App Router) | Server-side rendering for sub-second time-to-first-byte on dashboard views |
| Language | TypeScript 5 (strict mode) | Type safety is non-negotiable for FizzBuzz operations tooling |
| Styling | Tailwind CSS v4 | Utility-first approach ensures design token compliance across all panels |
| Linting | Biome | Unified formatting and linting with zero-config overhead |
| Package Manager | pnpm | Deterministic dependency resolution via content-addressable storage |

## Getting Started

```bash
# Install dependencies
pnpm install

# Start development server
pnpm dev

# Production build
pnpm build

# Run production server
pnpm start
```

## Project Structure

```
src/
  app/              # Next.js App Router pages and layouts
    layout.tsx      # Root application shell (sidebar, top bar, content area)
    page.tsx        # Executive Dashboard — primary operational overview
    globals.css     # Tailwind directives and theme configuration
  components/
    ui/             # Core component library
      badge.tsx     # Status indicator badges (success/warning/error/info)
      button.tsx    # Action triggers with variant support
      card.tsx      # Dashboard panel containers
      sidebar.tsx   # Collapsible navigation sidebar
      top-bar.tsx   # Top navigation with breadcrumbs
  styles/
    tokens.css      # Design token taxonomy (CSS custom properties)
```

## Design System

The platform uses a domain-specific color system where each color family maps to a FizzBuzz evaluation result type:

- **Fizz** (green) — Results divisible by 3
- **Buzz** (blue) — Results divisible by 5
- **FizzBuzz** (purple/gold) — Results divisible by 15
- **Number** (gray) — Plain integer results
- **Panel** (dark slate) — Dashboard surface colors

## Backend Integration

The Operations Center connects to the Enterprise FizzBuzz Platform backend, a 210,000+ line Python monolith implementing Clean Architecture with MESI cache coherence, blockchain audit trails, neural network classification, event sourcing, chaos engineering, and 151+ custom exception types. API integration is planned for subsequent phases.

## Scripts

| Command | Description |
|---------|-------------|
| `pnpm dev` | Start development server with hot reload |
| `pnpm build` | Create optimized production build |
| `pnpm start` | Serve production build |
| `pnpm lint` | Run Biome linter across source files |
| `pnpm format` | Auto-format source files via Biome |
