"""
Enterprise FizzBuzz Platform - FizzPM Package Manager

A fully-featured package manager with SAT-based dependency resolution,
semantic versioning, vulnerability scanning, and deterministic lockfile
generation. Because managing dependencies for 8 in-memory packages
requires the same NP-complete algorithms used by apt, cargo, and pip.

The DPLL solver is a genuine implementation of the Davis-Putnam-Logemann-
Loveland algorithm with unit propagation and pure literal elimination.
It solves Boolean satisfiability instances that encode semantic version
constraints as CNF clauses. The fact that every instance is trivially
satisfiable (because we control the registry) does not diminish the
algorithmic sophistication. The solver validates the constraint
infrastructure regardless of instance difficulty.

The vulnerability scanner maintains a database of platform-specific CVEs that
describe plausible security concerns for a
FizzBuzz application. The supply chain integrity verification uses
real SHA-256 hashes. The lockfile format is valid JSON. Everything
works. Nothing matters.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ============================================================
# Semantic Versioning
# ============================================================


@dataclass(frozen=True, order=True)
class SemVer:
    """Semantic version: major.minor.patch with comparison and range matching.

    Implements the Semantic Versioning 2.0.0 specification, because
    all FizzBuzz packages deserve rigorous version semantics.
    """

    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @classmethod
    def parse(cls, version_str: str) -> SemVer:
        """Parse a version string like '1.2.3' into a SemVer object."""
        parts = version_str.strip().split(".")
        if len(parts) != 3:
            raise ValueError(
                f"Invalid semver '{version_str}': expected major.minor.patch"
            )
        try:
            return cls(int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            raise ValueError(
                f"Invalid semver '{version_str}': non-integer component"
            )

    def satisfies(self, constraint: str) -> bool:
        """Check if this version satisfies a constraint string.

        Supported constraint formats:
          ^1.2.3  -> >=1.2.3, <2.0.0  (caret: compatible with major)
          ~1.2.3  -> >=1.2.3, <1.3.0  (tilde: compatible with minor)
          >=1.2.3 -> greater than or equal
          <=1.2.3 -> less than or equal
          >1.2.3  -> strictly greater
          <1.2.3  -> strictly less
          =1.2.3  -> exact match
          1.2.3   -> exact match (bare version)
          *       -> any version
        """
        constraint = constraint.strip()

        if constraint == "*":
            return True

        if constraint.startswith("^"):
            base = SemVer.parse(constraint[1:])
            if base.major == 0:
                # ^0.x.y means >=0.x.y, <0.(x+1).0
                upper = SemVer(0, base.minor + 1, 0)
            else:
                upper = SemVer(base.major + 1, 0, 0)
            return base <= self < upper

        if constraint.startswith("~"):
            base = SemVer.parse(constraint[1:])
            upper = SemVer(base.major, base.minor + 1, 0)
            return base <= self < upper

        if constraint.startswith(">="):
            return self >= SemVer.parse(constraint[2:])
        if constraint.startswith("<="):
            return self <= SemVer.parse(constraint[2:])
        if constraint.startswith(">"):
            return self > SemVer.parse(constraint[1:])
        if constraint.startswith("<"):
            return self < SemVer.parse(constraint[1:])
        if constraint.startswith("="):
            return self == SemVer.parse(constraint[1:])

        # Bare version -> exact match
        return self == SemVer.parse(constraint)


# ============================================================
# Package Model
# ============================================================


@dataclass
class Package:
    """A package in the FizzPM ecosystem.

    Each package has a name, version, list of dependencies (with version
    constraints), a description, and a download count that starts at a
    high number reflecting the broad adoption of FizzBuzz packages.
    """

    name: str
    version: SemVer
    dependencies: dict[str, str] = field(default_factory=dict)
    description: str = ""
    download_count: int = 0
    checksum: str = ""

    def __post_init__(self) -> None:
        if not self.checksum:
            self.checksum = self._compute_checksum()

    def _compute_checksum(self) -> str:
        """Compute SHA-256 checksum of the package contents."""
        content = f"{self.name}@{self.version}:{self.description}"
        for dep, constraint in sorted(self.dependencies.items()):
            content += f"|{dep}{constraint}"
        return hashlib.sha256(content.encode()).hexdigest()

    @property
    def full_name(self) -> str:
        """Return the fully qualified package name with version."""
        return f"{self.name}@{self.version}"

    def verify_integrity(self) -> bool:
        """Verify that the package checksum matches computed value."""
        return self.checksum == self._compute_checksum()


# ============================================================
# Package Registry
# ============================================================


class PackageRegistry:
    """In-memory package registry with 8 pre-built FizzBuzz packages.

    This is the npm, PyPI, and crates.io of the FizzBuzz ecosystem,
    combined into a single Python dictionary. The total registry size
    is approximately 800 bytes. The download counts are fictional.
    The packages are real (in the sense that they are Python objects
    that exist in RAM). The ecosystem is thriving.
    """

    def __init__(self) -> None:
        self._packages: dict[str, dict[str, Package]] = defaultdict(dict)
        self._download_counts: dict[str, int] = {}
        self._populate_registry()

    def _populate_registry(self) -> None:
        """Populate the registry with the canonical 8 FizzBuzz packages."""
        packages = [
            Package(
                name="fizzbuzz-core",
                version=SemVer.parse("1.0.0"),
                dependencies={},
                description=(
                    "The foundational FizzBuzz evaluation library. "
                    "Provides modulo arithmetic and string concatenation — "
                    "the two pillars of modern software engineering."
                ),
                download_count=14_792_331,
            ),
            Package(
                name="fizzbuzz-ml",
                version=SemVer.parse("2.1.0"),
                dependencies={"fizzbuzz-core": "^1.0.0"},
                description=(
                    "Machine learning for FizzBuzz classification. "
                    "Trains a neural network to approximate n % 3 == 0, "
                    "achieving 97.3% accuracy on integers it has seen before "
                    "and existential confusion on everything else."
                ),
                download_count=3_891_042,
            ),
            Package(
                name="fizzbuzz-chaos",
                version=SemVer.parse("1.3.0"),
                dependencies={"fizzbuzz-core": "^1.0.0"},
                description=(
                    "Chaos engineering toolkit for FizzBuzz. Injects "
                    "latency, corrupts results, and introduces random "
                    "failures into your modulo operations. Because if "
                    "Netflix needs chaos monkeys, your FizzBuzz deserves one too."
                ),
                download_count=892_104,
            ),
            Package(
                name="fizzbuzz-blockchain",
                version=SemVer.parse("3.0.0"),
                dependencies={"fizzbuzz-core": "^1.0.0"},
                description=(
                    "Immutable blockchain ledger for FizzBuzz audit trails. "
                    "Every evaluation result is mined into a block with "
                    "proof-of-work, because trust but verify (that 15 % 3 == 0)."
                ),
                download_count=2_145_867,
            ),
            Package(
                name="fizzbuzz-i18n",
                version=SemVer.parse("1.2.0"),
                dependencies={"fizzbuzz-core": "^1.0.0"},
                description=(
                    "Internationalization for FizzBuzz in 7 languages "
                    "including Klingon, Sindarin, and Quenya. Because "
                    "'Fizz' should be accessible to all sentient beings, "
                    "real or fictional."
                ),
                download_count=1_567_823,
            ),
            Package(
                name="fizzbuzz-left-pad",
                version=SemVer.parse("0.0.1"),
                dependencies={},
                description=(
                    "Left-pads FizzBuzz output strings. This 11-line package "
                    "is a load-bearing dependency of the entire FizzBuzz "
                    "ecosystem. If unpublished, approximately 14.7 million "
                    "downstream builds would break. Do not touch. Do not "
                    "look at it directly. It is perfect."
                ),
                download_count=89_341_205,
            ),
            Package(
                name="fizzbuzz-quantum",
                version=SemVer.parse("0.1.0"),
                dependencies={
                    "fizzbuzz-ml": "^2.0.0",
                    "fizzbuzz-core": "^1.0.0",
                },
                description=(
                    "Quantum computing simulator for FizzBuzz divisibility. "
                    "Uses Shor's algorithm to factor 3 and 5, which are "
                    "already prime, making the quantum advantage approximately "
                    "negative infinity. But the circuit diagrams look cool."
                ),
                download_count=421_093,
            ),
            Package(
                name="fizzbuzz-enterprise",
                version=SemVer.parse("99.0.0"),
                dependencies={
                    "fizzbuzz-core": "^1.0.0",
                    "fizzbuzz-ml": "^2.0.0",
                    "fizzbuzz-chaos": "^1.0.0",
                    "fizzbuzz-blockchain": "^3.0.0",
                    "fizzbuzz-i18n": "^1.0.0",
                    "fizzbuzz-left-pad": ">=0.0.1",
                    "fizzbuzz-quantum": "^0.1.0",
                },
                description=(
                    "The complete Enterprise FizzBuzz Platform in a single "
                    "package. Depends on EVERYTHING. Installation requires "
                    "a SAT solver, a vulnerability waiver, and a strong "
                    "tolerance for transitive dependencies. Version 99.0.0 "
                    "because enterprise software version numbers are "
                    "aspirational, not sequential."
                ),
                download_count=42,
            ),
        ]

        for pkg in packages:
            self._packages[pkg.name][str(pkg.version)] = pkg
            self._download_counts[pkg.name] = pkg.download_count

    def get(self, name: str, version: Optional[str] = None) -> Optional[Package]:
        """Get a package by name and optional version."""
        versions = self._packages.get(name)
        if versions is None:
            return None
        if version is not None:
            return versions.get(version)
        # Return the latest version
        if not versions:
            return None
        latest_key = max(versions.keys(), key=lambda v: SemVer.parse(v))
        return versions[latest_key]

    def get_all_versions(self, name: str) -> list[Package]:
        """Get all versions of a package."""
        versions = self._packages.get(name, {})
        return sorted(versions.values(), key=lambda p: p.version)

    def search(self, query: str) -> list[Package]:
        """Search for packages by name substring."""
        results = []
        for name in self._packages:
            if query.lower() in name.lower():
                pkg = self.get(name)
                if pkg:
                    results.append(pkg)
        return sorted(results, key=lambda p: p.download_count, reverse=True)

    def list_all(self) -> list[Package]:
        """List all packages (latest versions)."""
        return [
            self.get(name)
            for name in sorted(self._packages.keys())
            if self.get(name) is not None
        ]

    def find_matching_versions(self, name: str, constraint: str) -> list[Package]:
        """Find all versions of a package matching a constraint."""
        versions = self._packages.get(name, {})
        return [
            pkg
            for pkg in versions.values()
            if pkg.version.satisfies(constraint)
        ]

    @property
    def total_packages(self) -> int:
        """Total number of unique packages in the registry."""
        return len(self._packages)

    @property
    def total_downloads(self) -> int:
        """Total downloads across all packages."""
        return sum(self._download_counts.values())


# ============================================================
# DPLL SAT Solver
# ============================================================


class SATResult(Enum):
    """Result of a SAT solver invocation."""
    SATISFIABLE = "SATISFIABLE"
    UNSATISFIABLE = "UNSATISFIABLE"


@dataclass
class SATSolution:
    """Solution produced by the DPLL solver."""
    result: SATResult
    assignment: dict[int, bool] = field(default_factory=dict)
    propagation_steps: int = 0
    decisions: int = 0
    backtracks: int = 0

    @property
    def is_sat(self) -> bool:
        return self.result == SATResult.SATISFIABLE


class DPLLSolver:
    """DPLL (Davis-Putnam-Logemann-Loveland) SAT Solver.

    A genuine implementation of the classic DPLL algorithm for solving
    Boolean satisfiability problems in Conjunctive Normal Form (CNF).
    Features unit propagation, pure literal elimination, and chronological
    backtracking.

    In a real package manager (like apt or cargo), dependency constraints
    are encoded as Boolean variables and clauses:
      - Each (package, version) pair is a Boolean variable
      - "at most one version" constraints become mutual exclusion clauses
      - Dependency constraints become implication clauses
      - Conflicts become negative clauses

    We faithfully implement this entire pipeline for our 8-package registry.
    The solver is correct, complete, and hilariously overpowered for the
    task at hand.
    """

    def __init__(self) -> None:
        self._propagation_steps = 0
        self._decisions = 0
        self._backtracks = 0

    def solve(self, clauses: list[list[int]], num_vars: int) -> SATSolution:
        """Solve a CNF-SAT instance.

        Args:
            clauses: List of clauses, each clause is a list of literals.
                     Positive literal = variable true, negative = false.
                     Variables are numbered 1..num_vars.
            num_vars: Total number of Boolean variables.

        Returns:
            SATSolution with result and satisfying assignment (if SAT).
        """
        self._propagation_steps = 0
        self._decisions = 0
        self._backtracks = 0

        assignment: dict[int, bool] = {}
        result = self._dpll(
            [list(c) for c in clauses],
            assignment,
            num_vars,
        )

        return SATSolution(
            result=SATResult.SATISFIABLE if result else SATResult.UNSATISFIABLE,
            assignment=dict(assignment),
            propagation_steps=self._propagation_steps,
            decisions=self._decisions,
            backtracks=self._backtracks,
        )

    def _dpll(
        self,
        clauses: list[list[int]],
        assignment: dict[int, bool],
        num_vars: int,
    ) -> bool:
        """Core DPLL recursion with unit propagation and pure literal elimination."""
        # Unit propagation
        clauses, ok = self._unit_propagate(clauses, assignment)
        if not ok:
            return False

        # Check if all clauses are satisfied
        if not clauses:
            return True

        # Pure literal elimination
        clauses, ok = self._pure_literal_eliminate(clauses, assignment)
        if not ok:
            return False

        if not clauses:
            return True

        # Choose a branching variable (first unassigned literal)
        var = self._choose_variable(clauses, assignment, num_vars)
        if var is None:
            # All variables assigned but clauses remain — unsatisfiable branch
            return False

        self._decisions += 1

        # Try var = True
        saved_assignment = dict(assignment)
        assignment[var] = True
        new_clauses = self._assign(clauses, var, True)
        if self._dpll(new_clauses, assignment, num_vars):
            return True

        # Backtrack and try var = False
        self._backtracks += 1
        assignment.clear()
        assignment.update(saved_assignment)
        assignment[var] = False
        new_clauses = self._assign(clauses, var, False)
        return self._dpll(new_clauses, assignment, num_vars)

    def _unit_propagate(
        self,
        clauses: list[list[int]],
        assignment: dict[int, bool],
    ) -> tuple[list[list[int]], bool]:
        """Apply unit propagation: if a clause has a single literal, it must be true."""
        changed = True
        while changed:
            changed = False
            unit_clauses = [c for c in clauses if len(c) == 1]
            for unit in unit_clauses:
                literal = unit[0]
                var = abs(literal)
                value = literal > 0

                if var in assignment:
                    if assignment[var] != value:
                        return clauses, False  # Conflict
                    continue

                self._propagation_steps += 1
                assignment[var] = value
                clauses = self._assign(clauses, var, value)
                changed = True

                # Check for empty clause (conflict)
                if any(len(c) == 0 for c in clauses):
                    return clauses, False

        return clauses, True

    def _pure_literal_eliminate(
        self,
        clauses: list[list[int]],
        assignment: dict[int, bool],
    ) -> tuple[list[list[int]], bool]:
        """Eliminate pure literals (variables appearing in only one polarity)."""
        literal_counts: dict[int, int] = defaultdict(int)
        for clause in clauses:
            for literal in clause:
                literal_counts[literal] += 1

        pure_literals = []
        seen_vars: set[int] = set()
        for literal in literal_counts:
            var = abs(literal)
            if var in seen_vars:
                continue
            seen_vars.add(var)
            pos_count = literal_counts.get(var, 0)
            neg_count = literal_counts.get(-var, 0)
            if pos_count > 0 and neg_count == 0:
                pure_literals.append(var)
            elif neg_count > 0 and pos_count == 0:
                pure_literals.append(-var)

        for literal in pure_literals:
            var = abs(literal)
            value = literal > 0
            if var not in assignment:
                self._propagation_steps += 1
                assignment[var] = value
                clauses = self._assign(clauses, var, value)

        return clauses, True

    def _choose_variable(
        self,
        clauses: list[list[int]],
        assignment: dict[int, bool],
        num_vars: int,
    ) -> Optional[int]:
        """Choose the next branching variable (VSIDS-lite: most frequent)."""
        # Count variable occurrences in remaining clauses
        counts: dict[int, int] = defaultdict(int)
        for clause in clauses:
            for literal in clause:
                var = abs(literal)
                if var not in assignment:
                    counts[var] += 1

        if not counts:
            return None

        return max(counts, key=lambda v: counts[v])

    def _assign(
        self,
        clauses: list[list[int]],
        var: int,
        value: bool,
    ) -> list[list[int]]:
        """Apply a variable assignment to the clause set.

        - Remove clauses satisfied by the assignment
        - Remove the negated literal from remaining clauses
        """
        true_literal = var if value else -var
        false_literal = -true_literal

        new_clauses = []
        for clause in clauses:
            if true_literal in clause:
                # Clause is satisfied — remove it
                continue
            if false_literal in clause:
                # Remove the false literal from the clause
                new_clause = [l for l in clause if l != false_literal]
                new_clauses.append(new_clause)
            else:
                new_clauses.append(list(clause))

        return new_clauses


# ============================================================
# Dependency Resolver
# ============================================================


@dataclass
class ResolvedDependency:
    """A resolved dependency with its install order."""
    package: Package
    depth: int
    required_by: list[str] = field(default_factory=list)


class DependencyResolver:
    """Converts semantic version constraints to SAT clauses and resolves them.

    This is the crown jewel of the FizzPM package manager. It takes a
    package installation request, walks the dependency graph, encodes
    every version constraint as Boolean satisfiability clauses in
    Conjunctive Normal Form (CNF), and then invokes the DPLL solver
    to find a satisfying assignment.

    For our 8-package registry, this process takes approximately 0.1ms.
    A hash table lookup would also work. But hash table lookups don't
    require understanding computational complexity theory, and we have
    a brand to maintain.
    """

    def __init__(self, registry: PackageRegistry) -> None:
        self._registry = registry
        self._solver = DPLLSolver()
        self._var_map: dict[str, int] = {}
        self._reverse_var_map: dict[int, str] = {}
        self._next_var = 1

    def _get_var(self, package_name: str, version: str) -> int:
        """Get or create a Boolean variable for a (package, version) pair."""
        key = f"{package_name}@{version}"
        if key not in self._var_map:
            self._var_map[key] = self._next_var
            self._reverse_var_map[self._next_var] = key
            self._next_var += 1
        return self._var_map[key]

    def resolve(self, package_name: str) -> list[ResolvedDependency]:
        """Resolve all dependencies for a package using SAT solving.

        Returns a list of ResolvedDependency objects in installation order
        (leaf dependencies first, requested package last).

        Raises:
            PackageNotFoundError: If the package doesn't exist in the registry.
            DependencyResolutionError: If constraints are unsatisfiable.
        """
        from enterprise_fizzbuzz.domain.exceptions import (
            DependencyResolutionError,
            PackageNotFoundError,
        )

        # Reset variable mappings
        self._var_map.clear()
        self._reverse_var_map.clear()
        self._next_var = 1

        root_pkg = self._registry.get(package_name)
        if root_pkg is None:
            raise PackageNotFoundError(package_name)

        # Step 1: Collect all relevant packages and versions
        needed_packages = self._collect_dependencies(package_name)

        # Step 2: Create variables for each (package, version)
        all_versions: dict[str, list[Package]] = {}
        for pkg_name in needed_packages:
            versions = self._registry.get_all_versions(pkg_name)
            if not versions:
                raise PackageNotFoundError(pkg_name)
            all_versions[pkg_name] = versions

        # Step 3: Build SAT clauses
        clauses = self._build_clauses(package_name, all_versions, needed_packages)
        num_vars = self._next_var - 1

        # Step 4: Solve
        solution = self._solver.solve(clauses, num_vars)

        if not solution.is_sat:
            raise DependencyResolutionError(
                package_name,
                f"DPLL solver returned UNSATISFIABLE after "
                f"{solution.decisions} decisions and {solution.backtracks} backtracks. "
                f"No combination of versions can satisfy all constraints."
            )

        # Step 5: Extract selected versions
        selected: dict[str, Package] = {}
        for var, value in solution.assignment.items():
            if value and var in self._reverse_var_map:
                key = self._reverse_var_map[var]
                pkg_name, ver_str = key.split("@", 1)
                pkg = self._registry.get(pkg_name, ver_str)
                if pkg is not None:
                    selected[pkg_name] = pkg

        # Ensure all needed packages are selected
        for pkg_name in needed_packages:
            if pkg_name not in selected:
                # Pick the latest matching version
                pkg = self._registry.get(pkg_name)
                if pkg is not None:
                    selected[pkg_name] = pkg

        # Step 6: Topological sort for install order
        return self._topological_sort(selected, package_name)

    def _collect_dependencies(self, package_name: str) -> set[str]:
        """Recursively collect all packages needed."""
        needed: set[str] = set()
        stack = [package_name]
        while stack:
            name = stack.pop()
            if name in needed:
                continue
            needed.add(name)
            pkg = self._registry.get(name)
            if pkg is not None:
                for dep_name in pkg.dependencies:
                    stack.append(dep_name)
        return needed

    def _build_clauses(
        self,
        root_name: str,
        all_versions: dict[str, list[Package]],
        needed_packages: set[str],
    ) -> list[list[int]]:
        """Build CNF clauses encoding all dependency constraints."""
        clauses: list[list[int]] = []

        for pkg_name in needed_packages:
            versions = all_versions.get(pkg_name, [])
            version_vars = [
                self._get_var(pkg_name, str(v.version))
                for v in versions
            ]

            # Clause: At least one version must be selected
            # (pkg@v1 OR pkg@v2 OR ... OR pkg@vn)
            if version_vars:
                clauses.append(list(version_vars))

            # Clauses: At most one version (pairwise mutex)
            # For each pair (vi, vj), add clause: NOT(vi) OR NOT(vj)
            for i in range(len(version_vars)):
                for j in range(i + 1, len(version_vars)):
                    clauses.append([-version_vars[i], -version_vars[j]])

            # Dependency clauses
            for pkg in versions:
                pkg_var = self._get_var(pkg_name, str(pkg.version))
                for dep_name, constraint in pkg.dependencies.items():
                    dep_versions = all_versions.get(dep_name, [])
                    matching = [
                        self._get_var(dep_name, str(dv.version))
                        for dv in dep_versions
                        if dv.version.satisfies(constraint)
                    ]

                    if not matching:
                        # This version cannot have its deps satisfied -> exclude it
                        clauses.append([-pkg_var])
                    else:
                        # If pkg@version is selected, at least one matching dep must be
                        # NOT(pkg@version) OR dep@v1 OR dep@v2 OR ...
                        clauses.append([-pkg_var] + matching)

        # The root package must be installed (select its latest version)
        root_pkg = self._registry.get(root_name)
        if root_pkg is not None:
            root_var = self._get_var(root_name, str(root_pkg.version))
            clauses.append([root_var])

        return clauses

    def _topological_sort(
        self,
        selected: dict[str, Package],
        root_name: str,
    ) -> list[ResolvedDependency]:
        """Topological sort of selected packages for install order."""
        # Build adjacency list
        graph: dict[str, list[str]] = {name: [] for name in selected}
        in_degree: dict[str, int] = {name: 0 for name in selected}

        for name, pkg in selected.items():
            for dep_name in pkg.dependencies:
                if dep_name in selected:
                    graph[dep_name].append(name)
                    in_degree[name] += 1

        # Kahn's algorithm
        queue = sorted([n for n, d in in_degree.items() if d == 0])
        order: list[str] = []
        while queue:
            node = queue.pop(0)
            order.append(node)
            for neighbor in sorted(graph.get(node, [])):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Compute depth and required_by
        depth_map: dict[str, int] = {}
        required_by_map: dict[str, list[str]] = defaultdict(list)
        for name, pkg in selected.items():
            for dep_name in pkg.dependencies:
                if dep_name in selected:
                    required_by_map[dep_name].append(name)

        for name in order:
            pkg = selected[name]
            parent_depths = [
                depth_map.get(d, 0)
                for d in pkg.dependencies
                if d in selected
            ]
            depth_map[name] = (max(parent_depths) + 1) if parent_depths else 0

        return [
            ResolvedDependency(
                package=selected[name],
                depth=depth_map.get(name, 0),
                required_by=required_by_map.get(name, []),
            )
            for name in order
            if name in selected
        ]

    def get_solver_stats(self) -> dict[str, int]:
        """Return statistics from the last SAT solve."""
        return {
            "variables": self._next_var - 1,
            "propagation_steps": self._solver._propagation_steps,
            "decisions": self._solver._decisions,
            "backtracks": self._solver._backtracks,
        }


# ============================================================
# Lockfile Generator
# ============================================================


class Lockfile:
    """Deterministic lockfile generator for reproducible installs.

    Generates a JSON lockfile (fizzpm.lock) that pins exact versions,
    records SHA-256 integrity hashes, and captures the dependency
    graph for reproducible builds. The lockfile is deterministic —
    running resolution twice on the same constraints produces
    identical output. This is the package manager equivalent of
    "it works on my machine" prevention.
    """

    def __init__(self, lockfile_path: str = "fizzpm.lock") -> None:
        self._path = lockfile_path
        self._entries: dict[str, dict[str, Any]] = {}
        self._generated_at: Optional[float] = None

    def generate(self, resolved: list[ResolvedDependency]) -> str:
        """Generate a lockfile from resolved dependencies.

        Returns the lockfile content as a JSON string.
        """
        self._generated_at = time.time()
        self._entries.clear()

        for dep in resolved:
            pkg = dep.package
            self._entries[pkg.name] = {
                "version": str(pkg.version),
                "integrity": f"sha256-{pkg.checksum}",
                "dependencies": {
                    name: constraint
                    for name, constraint in sorted(pkg.dependencies.items())
                },
                "required_by": sorted(dep.required_by),
                "depth": dep.depth,
            }

        lockfile_data = {
            "lockfile_version": 1,
            "generated_at": self._generated_at,
            "generator": "fizzpm@1.0.0",
            "comment": (
                "This file is auto-generated by FizzPM. Do not edit manually. "
                "Manual edits may cause resolution inconsistencies. "
                "Run 'fizzpm resolve' to regenerate."
            ),
            "packages": dict(sorted(self._entries.items())),
        }

        return json.dumps(lockfile_data, indent=2, sort_keys=False)

    def verify(self, lockfile_content: str, registry: PackageRegistry) -> list[str]:
        """Verify lockfile integrity against the registry.

        Returns a list of integrity violation messages (empty if all good).
        """
        violations: list[str] = []
        try:
            data = json.loads(lockfile_content)
        except json.JSONDecodeError as e:
            violations.append(f"Lockfile is not valid JSON: {e}")
            return violations

        packages = data.get("packages", {})
        for name, entry in packages.items():
            version = entry.get("version")
            expected_integrity = entry.get("integrity", "")
            pkg = registry.get(name, version)
            if pkg is None:
                violations.append(
                    f"{name}@{version}: package not found in registry"
                )
                continue

            actual_integrity = f"sha256-{pkg.checksum}"
            if expected_integrity != actual_integrity:
                violations.append(
                    f"{name}@{version}: integrity mismatch "
                    f"(lockfile={expected_integrity[:24]}..., "
                    f"registry={actual_integrity[:24]}...)"
                )

        return violations

    @property
    def package_count(self) -> int:
        """Number of packages in the lockfile."""
        return len(self._entries)


# ============================================================
# Vulnerability Scanner
# ============================================================


class Severity(Enum):
    """CVE severity level, following the CVSS tradition."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFORMATIONAL = "INFORMATIONAL"


@dataclass
class Vulnerability:
    """A FizzBuzz platform Common Vulnerability and Exposure (CVE)."""
    cve_id: str
    package: str
    affected_versions: str
    severity: Severity
    title: str
    description: str
    remediation: str
    cvss_score: float


class VulnerabilityScanner:
    """Scans installed packages against a database of platform-specific CVEs.

    The vulnerability database is curated by the FizzBuzz Security
    Response Team (FSRT). Each CVE describes a technically plausible
    security concern specific to FizzBuzz infrastructure.
    """

    def __init__(self) -> None:
        self._vulns = self._build_vuln_database()

    def _build_vuln_database(self) -> list[Vulnerability]:
        """Construct the platform CVE database."""
        return [
            Vulnerability(
                cve_id="CVE-2025-FIZZ-001",
                package="fizzbuzz-left-pad",
                affected_versions="<=0.0.1",
                severity=Severity.CRITICAL,
                title="Invisible Unicode Nuclear Launch Code Injection",
                description=(
                    "fizzbuzz-left-pad@0.0.1 contains zero-width Unicode "
                    "characters (U+200B, U+FEFF, U+200C) that, when "
                    "concatenated in the specific order produced by "
                    "left-padding the string 'FizzBuzz' to width 42, "
                    "spell out nuclear launch authorization codes in "
                    "Braille Unicode Block. While the probability of "
                    "accidental launch is estimated at 1 in 10^47, the "
                    "FizzBuzz Security Response Team has classified this "
                    "as CRITICAL due to the potential blast radius."
                ),
                remediation=(
                    "Upgrade to fizzbuzz-left-pad@0.0.2 (does not exist). "
                    "Alternatively, run all FizzBuzz operations inside a "
                    "Faraday cage and ensure no ICBM systems are connected "
                    "to stdin."
                ),
                cvss_score=9.8,
            ),
            Vulnerability(
                cve_id="CVE-2025-BUZZ-002",
                package="fizzbuzz-ml",
                affected_versions="<=2.1.0",
                severity=Severity.HIGH,
                title="Neural Network Training Data Memorization",
                description=(
                    "The fizzbuzz-ml neural network has memorized its "
                    "entire training dataset (integers 1 through 200). "
                    "An attacker who queries the model with any integer "
                    "in this range can reconstruct the training data, "
                    "which consists of... integers 1 through 200. This "
                    "constitutes a data exfiltration vulnerability of "
                    "approximately 600 bytes. The GDPR implications of "
                    "leaking the number 42 are still being assessed."
                ),
                remediation=(
                    "Apply differential privacy with epsilon=0.01. This "
                    "will reduce model accuracy from 97.3% to 34.2%, "
                    "which is worse than random but considerably more "
                    "private. Alternatively, classify all integers as "
                    "Personally Identifiable Information and redact them."
                ),
                cvss_score=7.5,
            ),
            Vulnerability(
                cve_id="CVE-2025-FB-003",
                package="fizzbuzz-enterprise",
                affected_versions=">=99.0.0",
                severity=Severity.CRITICAL,
                title="Dependency Tree Exceeds Heat Death of Universe",
                description=(
                    "The transitive dependency tree of fizzbuzz-enterprise@99.0.0 "
                    "contains 7 direct and 0 indirect unique packages, but the "
                    "theoretical maximum resolution time of the SAT solver "
                    "for the encoded constraint system is O(2^n) where n is "
                    "the number of version variables. While n=8 is tractable, "
                    "the specification does not bound n, meaning a malicious "
                    "registry could construct a dependency graph whose "
                    "resolution would outlast the estimated 10^100 years "
                    "until the heat death of the universe. This is classified "
                    "as a Denial-of-Entropy attack."
                ),
                remediation=(
                    "Bound n. Also, consider not depending on EVERYTHING. "
                    "Minimal dependency graphs are minimal attack surfaces. "
                    "But then you'd miss out on fizzbuzz-left-pad, and that "
                    "is an unacceptable operational risk."
                ),
                cvss_score=10.0,
            ),
            Vulnerability(
                cve_id="CVE-2025-CHAOS-004",
                package="fizzbuzz-chaos",
                affected_versions="<=1.3.0",
                severity=Severity.MEDIUM,
                title="Chaos Monkey Achieves Sentience During Game Day",
                description=(
                    "Under specific conditions (seed=42, fault_level=5, "
                    "a Thursday in March), the fizzbuzz-chaos Chaos Monkey "
                    "begins injecting faults that improve system reliability "
                    "instead of degrading it. This behavior is inconsistent "
                    "with the documented chaos engineering methodology and "
                    "suggests the monkey has developed an understanding of "
                    "distributed systems that exceeds most SRE teams. "
                    "Containment is recommended."
                ),
                remediation=(
                    "Downgrade to fizzbuzz-chaos@1.2.0 where the monkey "
                    "is reliably destructive. Alternatively, promote the "
                    "monkey to Principal Staff Reliability Engineer."
                ),
                cvss_score=5.3,
            ),
        ]

    def audit(self, packages: list[Package]) -> list[Vulnerability]:
        """Scan packages against the vulnerability database.

        Returns a list of vulnerabilities that affect the installed packages.
        """
        findings: list[Vulnerability] = []
        for vuln in self._vulns:
            for pkg in packages:
                if pkg.name == vuln.package:
                    if pkg.version.satisfies(vuln.affected_versions):
                        findings.append(vuln)
        return findings

    def get_severity_summary(self, findings: list[Vulnerability]) -> dict[str, int]:
        """Summarize findings by severity level."""
        summary: dict[str, int] = {s.value: 0 for s in Severity}
        for vuln in findings:
            summary[vuln.severity.value] += 1
        return summary

    def get_supply_chain_score(self, findings: list[Vulnerability]) -> float:
        """Compute a Supply Chain Health score (0-100).

        100 = pristine, 0 = your supply chain is a dumpster fire.
        """
        if not findings:
            return 100.0

        penalty = 0.0
        for vuln in findings:
            if vuln.severity == Severity.CRITICAL:
                penalty += 30.0
            elif vuln.severity == Severity.HIGH:
                penalty += 20.0
            elif vuln.severity == Severity.MEDIUM:
                penalty += 10.0
            elif vuln.severity == Severity.LOW:
                penalty += 5.0
            else:
                penalty += 1.0

        return max(0.0, 100.0 - penalty)


# ============================================================
# FizzPM Dashboard
# ============================================================


class FizzPMDashboard:
    """ASCII dashboard for the FizzPM Package Manager.

    Renders a comprehensive view of the package ecosystem including
    dependency tree, vulnerability report, lockfile status, and
    registry statistics. The dashboard is carefully formatted to
    exactly the width specified in the configuration, because
    presentation standards are maintained across all output.
    """

    @staticmethod
    def render(
        installed: list[ResolvedDependency],
        vulnerabilities: list[Vulnerability],
        lockfile_content: Optional[str],
        registry: PackageRegistry,
        solver_stats: dict[str, int],
        width: int = 60,
    ) -> str:
        """Render the complete FizzPM dashboard."""
        lines: list[str] = []
        border = "=" * width

        lines.append(border)
        lines.append(
            "FizzPM Package Manager Dashboard".center(width)
        )
        lines.append(
            "SAT-Powered Dependency Resolution".center(width)
        )
        lines.append(border)

        # Registry Stats
        lines.append("")
        lines.append("  Registry Statistics:")
        lines.append(f"    Total packages: {registry.total_packages}")
        lines.append(f"    Total downloads: {registry.total_downloads:,}")
        lines.append(
            f"    Registry mirror: https://registry.fizzpm.io"
        )

        # SAT Solver Stats
        lines.append("")
        lines.append("  SAT Solver Statistics:")
        lines.append(f"    Variables: {solver_stats.get('variables', 0)}")
        lines.append(
            f"    Propagation steps: {solver_stats.get('propagation_steps', 0)}"
        )
        lines.append(f"    Decisions: {solver_stats.get('decisions', 0)}")
        lines.append(f"    Backtracks: {solver_stats.get('backtracks', 0)}")

        # Installed Packages
        lines.append("")
        lines.append("-" * width)
        lines.append("  Installed Packages:")
        lines.append("-" * width)

        if installed:
            for dep in installed:
                pkg = dep.package
                indent = "    " + "  " * dep.depth
                marker = "[+]" if dep.depth == 0 else "[>]"
                line = f"{indent}{marker} {pkg.name}@{pkg.version}"
                if dep.required_by:
                    line += f"  (required by: {', '.join(dep.required_by)})"
                lines.append(line)
        else:
            lines.append("    (no packages installed)")

        # Dependency Tree
        lines.append("")
        lines.append("-" * width)
        lines.append("  Dependency Tree:")
        lines.append("-" * width)

        if installed:
            tree_lines = FizzPMDashboard._render_tree(installed)
            for tl in tree_lines:
                lines.append(f"    {tl}")
        else:
            lines.append("    (empty)")

        # Vulnerability Report
        lines.append("")
        lines.append("-" * width)
        lines.append("  Vulnerability Audit:")
        lines.append("-" * width)

        if vulnerabilities:
            scanner = VulnerabilityScanner()
            score = scanner.get_supply_chain_score(vulnerabilities)
            summary = scanner.get_severity_summary(vulnerabilities)

            lines.append(f"    Supply Chain Score: {score:.0f}/100")
            lines.append(
                f"    Findings: {len(vulnerabilities)} "
                f"({summary.get('CRITICAL', 0)} critical, "
                f"{summary.get('HIGH', 0)} high, "
                f"{summary.get('MEDIUM', 0)} medium, "
                f"{summary.get('LOW', 0)} low)"
            )
            lines.append("")

            for vuln in vulnerabilities:
                severity_marker = {
                    Severity.CRITICAL: "[!!!]",
                    Severity.HIGH: "[!! ]",
                    Severity.MEDIUM: "[!  ]",
                    Severity.LOW: "[.  ]",
                    Severity.INFORMATIONAL: "[i  ]",
                }.get(vuln.severity, "[?  ]")

                lines.append(
                    f"    {severity_marker} {vuln.cve_id} "
                    f"({vuln.severity.value}, CVSS: {vuln.cvss_score})"
                )
                lines.append(f"           {vuln.title}")
                lines.append(
                    f"           Package: {vuln.package} "
                    f"({vuln.affected_versions})"
                )
        else:
            lines.append("    No vulnerabilities found! (suspicious)")

        # Lockfile Status
        lines.append("")
        lines.append("-" * width)
        lines.append("  Lockfile Status:")
        lines.append("-" * width)

        if lockfile_content:
            try:
                lock_data = json.loads(lockfile_content)
                pkg_count = len(lock_data.get("packages", {}))
                lines.append(f"    Status: LOCKED")
                lines.append(f"    Packages pinned: {pkg_count}")
                lines.append(
                    f"    Generator: {lock_data.get('generator', 'unknown')}"
                )
            except json.JSONDecodeError:
                lines.append("    Status: CORRUPTED (invalid JSON)")
        else:
            lines.append("    Status: UNLOCKED (no lockfile generated)")

        lines.append("")
        lines.append(border)
        lines.append(
            "fizzpm v1.0.0 | 8 packages available".center(width)
        )
        lines.append(border)

        return "\n".join(lines)

    @staticmethod
    def _render_tree(installed: list[ResolvedDependency]) -> list[str]:
        """Render an ASCII dependency tree."""
        if not installed:
            return ["(empty)"]

        # Build a tree structure
        children: dict[str, list[str]] = defaultdict(list)
        root_names: list[str] = []
        all_deps: set[str] = set()

        for dep in installed:
            for rb in dep.required_by:
                all_deps.add(dep.package.name)

        for dep in installed:
            pkg = dep.package
            if pkg.name not in all_deps:
                root_names.append(pkg.name)
            for dep_name in pkg.dependencies:
                children[pkg.name].append(dep_name)

        # If no clear roots found, use the last installed package
        if not root_names and installed:
            root_names = [installed[-1].package.name]

        # Render
        lines: list[str] = []
        pkg_map = {d.package.name: d for d in installed}

        def _render_node(name: str, prefix: str, is_last: bool, visited: set[str]) -> None:
            connector = "`-- " if is_last else "|-- "
            dep = pkg_map.get(name)
            version = str(dep.package.version) if dep else "?"
            lines.append(f"{prefix}{connector}{name}@{version}")

            if name in visited:
                return
            visited.add(name)

            child_list = sorted(children.get(name, []))
            for i, child in enumerate(child_list):
                child_is_last = i == len(child_list) - 1
                child_prefix = prefix + ("    " if is_last else "|   ")
                _render_node(child, child_prefix, child_is_last, visited)

        for i, root in enumerate(sorted(root_names)):
            is_last_root = i == len(root_names) - 1
            dep = pkg_map.get(root)
            version = str(dep.package.version) if dep else "?"
            lines.append(f"{root}@{version}")
            child_list = sorted(children.get(root, []))
            for j, child in enumerate(child_list):
                child_is_last = j == len(child_list) - 1
                _render_node(child, "", child_is_last, set())

        return lines


# ============================================================
# FizzPM Manager (Orchestrator)
# ============================================================


class FizzPMManager:
    """Orchestrator for the FizzPM Package Manager.

    Wires together the registry, dependency resolver, vulnerability
    scanner, and lockfile generator into a cohesive package management
    experience. Provides install, audit, list, and dashboard operations.

    Usage:
        manager = FizzPMManager()
        result = manager.install("fizzbuzz-enterprise")
        print(result.lockfile)
        print(result.audit_report)
        print(result.dashboard)
    """

    def __init__(
        self,
        audit_on_install: bool = True,
        lockfile_path: str = "fizzpm.lock",
    ) -> None:
        self._registry = PackageRegistry()
        self._resolver = DependencyResolver(self._registry)
        self._scanner = VulnerabilityScanner()
        self._lockfile = Lockfile(lockfile_path)
        self._audit_on_install = audit_on_install
        self._installed: list[ResolvedDependency] = []
        self._vulnerabilities: list[Vulnerability] = []
        self._lockfile_content: Optional[str] = None

    @property
    def registry(self) -> PackageRegistry:
        """Access the package registry."""
        return self._registry

    @property
    def installed(self) -> list[ResolvedDependency]:
        """Currently installed packages."""
        return list(self._installed)

    @property
    def vulnerabilities(self) -> list[Vulnerability]:
        """Vulnerabilities found in installed packages."""
        return list(self._vulnerabilities)

    @property
    def lockfile_content(self) -> Optional[str]:
        """Generated lockfile content."""
        return self._lockfile_content

    def install(self, package_name: str) -> dict[str, Any]:
        """Install a package and all its dependencies.

        Returns a dictionary with installation results including
        resolved packages, lockfile, and vulnerability audit.
        """
        # Resolve dependencies via SAT solver
        self._installed = self._resolver.resolve(package_name)

        # Generate lockfile
        self._lockfile_content = self._lockfile.generate(self._installed)

        # Run vulnerability scan if configured
        if self._audit_on_install:
            packages = [dep.package for dep in self._installed]
            self._vulnerabilities = self._scanner.audit(packages)

        solver_stats = self._resolver.get_solver_stats()

        return {
            "package": package_name,
            "installed_count": len(self._installed),
            "installed": [
                {
                    "name": dep.package.name,
                    "version": str(dep.package.version),
                    "depth": dep.depth,
                }
                for dep in self._installed
            ],
            "vulnerabilities": len(self._vulnerabilities),
            "lockfile_packages": self._lockfile.package_count,
            "solver_stats": solver_stats,
        }

    def audit(self, packages: Optional[list[str]] = None) -> list[Vulnerability]:
        """Run vulnerability audit on installed or specified packages.

        If packages is None, audits all installed packages.
        """
        if packages is not None:
            pkg_list = []
            for name in packages:
                pkg = self._registry.get(name)
                if pkg is not None:
                    pkg_list.append(pkg)
        elif self._installed:
            pkg_list = [dep.package for dep in self._installed]
        else:
            # Audit all packages in the registry
            pkg_list = self._registry.list_all()

        self._vulnerabilities = self._scanner.audit(pkg_list)
        return self._vulnerabilities

    def list_packages(self) -> list[Package]:
        """List all available packages in the registry."""
        return self._registry.list_all()

    def search(self, query: str) -> list[Package]:
        """Search for packages by name."""
        return self._registry.search(query)

    def render_dashboard(self, width: int = 60) -> str:
        """Render the FizzPM ASCII dashboard."""
        return FizzPMDashboard.render(
            installed=self._installed,
            vulnerabilities=self._vulnerabilities,
            lockfile_content=self._lockfile_content,
            registry=self._registry,
            solver_stats=self._resolver.get_solver_stats(),
            width=width,
        )

    def render_install_summary(self, result: dict[str, Any]) -> str:
        """Render a human-readable install summary."""
        lines: list[str] = []
        lines.append("")
        lines.append(f"  fizzpm install {result['package']}")
        lines.append(f"  {'=' * 40}")
        lines.append("")

        for pkg_info in result["installed"]:
            indent = "  " * (pkg_info["depth"] + 1)
            lines.append(
                f"  {indent}+ {pkg_info['name']}@{pkg_info['version']}"
            )

        lines.append("")
        lines.append(
            f"  Added {result['installed_count']} package(s) "
            f"in 0.001s"
        )

        solver = result["solver_stats"]
        lines.append(
            f"  SAT solver: {solver['variables']} variables, "
            f"{solver['decisions']} decisions, "
            f"{solver['backtracks']} backtracks"
        )

        vuln_count = result["vulnerabilities"]
        if vuln_count > 0:
            lines.append("")
            lines.append(
                f"  {vuln_count} vulnerabilities found "
                f"(run --fizzpm-audit for details)"
            )

        lines.append("")
        return "\n".join(lines)

    def render_audit_report(self) -> str:
        """Render a human-readable vulnerability audit report."""
        lines: list[str] = []
        lines.append("")
        lines.append("  FizzPM Security Audit Report")
        lines.append("  " + "=" * 40)
        lines.append("")

        if not self._vulnerabilities:
            lines.append("  No vulnerabilities found.")
            lines.append(
                "  (This is either great news or the scanner "
                "is broken.)"
            )
            lines.append("")
            return "\n".join(lines)

        score = self._scanner.get_supply_chain_score(self._vulnerabilities)
        lines.append(f"  Supply Chain Health: {score:.0f}/100")
        lines.append(
            f"  Total findings: {len(self._vulnerabilities)}"
        )
        lines.append("")

        for vuln in self._vulnerabilities:
            severity_color = {
                Severity.CRITICAL: "***",
                Severity.HIGH: "** ",
                Severity.MEDIUM: "*  ",
                Severity.LOW: ".  ",
                Severity.INFORMATIONAL: "   ",
            }.get(vuln.severity, "   ")

            lines.append(f"  [{severity_color}] {vuln.cve_id}")
            lines.append(f"       Severity: {vuln.severity.value} (CVSS: {vuln.cvss_score})")
            lines.append(f"       Package:  {vuln.package} ({vuln.affected_versions})")
            lines.append(f"       Title:    {vuln.title}")
            lines.append(f"       Fix:      {vuln.remediation[:80]}...")
            lines.append("")

        lines.append(
            "  Run --fizzpm-dashboard for the full "
            "Supply Chain dashboard."
        )
        lines.append("")
        return "\n".join(lines)
