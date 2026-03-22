"""
Enterprise FizzBuzz Platform - FizzPM Package Manager Test Suite

Comprehensive tests for the SAT-based dependency resolution engine,
semantic versioning, vulnerability scanning, lockfile generation,
and the FizzPM dashboard. Because testing a package manager that
manages packages for a FizzBuzz platform is testing all the way down.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.package_manager import (
    DependencyResolver,
    DPLLSolver,
    FizzPMDashboard,
    FizzPMManager,
    Lockfile,
    Package,
    PackageRegistry,
    ResolvedDependency,
    SATResult,
    SATSolution,
    SemVer,
    Severity,
    Vulnerability,
    VulnerabilityScanner,
)
from enterprise_fizzbuzz.domain.exceptions import (
    DependencyResolutionError,
    PackageIntegrityError,
    PackageManagerError,
    PackageNotFoundError,
    PackageVersionConflictError,
)


# ============================================================
# SemVer Tests
# ============================================================


class TestSemVer:
    """Tests for semantic version parsing, comparison, and constraint matching."""

    def test_parse_valid(self):
        v = SemVer.parse("1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3

    def test_parse_zero_version(self):
        v = SemVer.parse("0.0.0")
        assert v == SemVer(0, 0, 0)

    def test_parse_large_version(self):
        v = SemVer.parse("99.0.0")
        assert v.major == 99

    def test_parse_invalid_too_few_parts(self):
        with pytest.raises(ValueError, match="expected major.minor.patch"):
            SemVer.parse("1.2")

    def test_parse_invalid_too_many_parts(self):
        with pytest.raises(ValueError, match="expected major.minor.patch"):
            SemVer.parse("1.2.3.4")

    def test_parse_invalid_non_integer(self):
        with pytest.raises(ValueError, match="non-integer"):
            SemVer.parse("a.b.c")

    def test_str_representation(self):
        assert str(SemVer(1, 2, 3)) == "1.2.3"

    def test_comparison_equal(self):
        assert SemVer(1, 0, 0) == SemVer(1, 0, 0)

    def test_comparison_less_than_major(self):
        assert SemVer(1, 0, 0) < SemVer(2, 0, 0)

    def test_comparison_less_than_minor(self):
        assert SemVer(1, 0, 0) < SemVer(1, 1, 0)

    def test_comparison_less_than_patch(self):
        assert SemVer(1, 0, 0) < SemVer(1, 0, 1)

    def test_comparison_ordering(self):
        versions = [
            SemVer(2, 0, 0),
            SemVer(0, 1, 0),
            SemVer(1, 0, 0),
            SemVer(1, 1, 0),
        ]
        sorted_versions = sorted(versions)
        assert sorted_versions == [
            SemVer(0, 1, 0),
            SemVer(1, 0, 0),
            SemVer(1, 1, 0),
            SemVer(2, 0, 0),
        ]

    def test_satisfies_wildcard(self):
        assert SemVer(99, 0, 0).satisfies("*")

    def test_satisfies_exact_match(self):
        assert SemVer(1, 2, 3).satisfies("1.2.3")
        assert not SemVer(1, 2, 4).satisfies("1.2.3")

    def test_satisfies_exact_with_equals(self):
        assert SemVer(1, 2, 3).satisfies("=1.2.3")
        assert not SemVer(1, 2, 4).satisfies("=1.2.3")

    def test_satisfies_caret(self):
        # ^1.2.3 means >=1.2.3, <2.0.0
        assert SemVer(1, 2, 3).satisfies("^1.2.3")
        assert SemVer(1, 9, 9).satisfies("^1.2.3")
        assert not SemVer(2, 0, 0).satisfies("^1.2.3")
        assert not SemVer(1, 2, 2).satisfies("^1.2.3")

    def test_satisfies_caret_major_zero(self):
        # ^0.2.3 means >=0.2.3, <0.3.0
        assert SemVer(0, 2, 3).satisfies("^0.2.3")
        assert SemVer(0, 2, 9).satisfies("^0.2.3")
        assert not SemVer(0, 3, 0).satisfies("^0.2.3")

    def test_satisfies_tilde(self):
        # ~1.2.3 means >=1.2.3, <1.3.0
        assert SemVer(1, 2, 3).satisfies("~1.2.3")
        assert SemVer(1, 2, 9).satisfies("~1.2.3")
        assert not SemVer(1, 3, 0).satisfies("~1.2.3")
        assert not SemVer(1, 2, 2).satisfies("~1.2.3")

    def test_satisfies_greater_equal(self):
        assert SemVer(1, 0, 0).satisfies(">=1.0.0")
        assert SemVer(2, 0, 0).satisfies(">=1.0.0")
        assert not SemVer(0, 9, 9).satisfies(">=1.0.0")

    def test_satisfies_less_equal(self):
        assert SemVer(1, 0, 0).satisfies("<=1.0.0")
        assert SemVer(0, 9, 9).satisfies("<=1.0.0")
        assert not SemVer(1, 0, 1).satisfies("<=1.0.0")

    def test_satisfies_greater(self):
        assert SemVer(1, 0, 1).satisfies(">1.0.0")
        assert not SemVer(1, 0, 0).satisfies(">1.0.0")

    def test_satisfies_less(self):
        assert SemVer(0, 9, 9).satisfies("<1.0.0")
        assert not SemVer(1, 0, 0).satisfies("<1.0.0")

    def test_frozen_hashable(self):
        """SemVer should be hashable (frozen dataclass)."""
        s = {SemVer(1, 0, 0), SemVer(1, 0, 0), SemVer(2, 0, 0)}
        assert len(s) == 2


# ============================================================
# Package Tests
# ============================================================


class TestPackage:
    """Tests for the Package dataclass."""

    def test_create_package(self):
        pkg = Package(
            name="test-pkg",
            version=SemVer(1, 0, 0),
            description="A test package",
        )
        assert pkg.name == "test-pkg"
        assert pkg.version == SemVer(1, 0, 0)

    def test_checksum_auto_computed(self):
        pkg = Package(
            name="test-pkg",
            version=SemVer(1, 0, 0),
        )
        assert len(pkg.checksum) == 64  # SHA-256 hex digest

    def test_checksum_deterministic(self):
        pkg1 = Package(name="test", version=SemVer(1, 0, 0), description="hello")
        pkg2 = Package(name="test", version=SemVer(1, 0, 0), description="hello")
        assert pkg1.checksum == pkg2.checksum

    def test_checksum_changes_with_content(self):
        pkg1 = Package(name="test", version=SemVer(1, 0, 0), description="hello")
        pkg2 = Package(name="test", version=SemVer(1, 0, 0), description="world")
        assert pkg1.checksum != pkg2.checksum

    def test_full_name(self):
        pkg = Package(name="fizzbuzz-core", version=SemVer(1, 0, 0))
        assert pkg.full_name == "fizzbuzz-core@1.0.0"

    def test_verify_integrity_valid(self):
        pkg = Package(name="test", version=SemVer(1, 0, 0))
        assert pkg.verify_integrity()

    def test_verify_integrity_tampered(self):
        pkg = Package(name="test", version=SemVer(1, 0, 0))
        pkg.checksum = "0" * 64
        assert not pkg.verify_integrity()

    def test_package_with_dependencies(self):
        pkg = Package(
            name="fizzbuzz-ml",
            version=SemVer(2, 1, 0),
            dependencies={"fizzbuzz-core": "^1.0.0"},
        )
        assert "fizzbuzz-core" in pkg.dependencies


# ============================================================
# PackageRegistry Tests
# ============================================================


class TestPackageRegistry:
    """Tests for the in-memory package registry."""

    def test_registry_has_eight_packages(self):
        reg = PackageRegistry()
        assert reg.total_packages == 8

    def test_get_existing_package(self):
        reg = PackageRegistry()
        pkg = reg.get("fizzbuzz-core")
        assert pkg is not None
        assert pkg.name == "fizzbuzz-core"
        assert pkg.version == SemVer(1, 0, 0)

    def test_get_nonexistent_package(self):
        reg = PackageRegistry()
        assert reg.get("fizzbuzz-unicorn") is None

    def test_get_specific_version(self):
        reg = PackageRegistry()
        pkg = reg.get("fizzbuzz-core", "1.0.0")
        assert pkg is not None
        assert str(pkg.version) == "1.0.0"

    def test_get_nonexistent_version(self):
        reg = PackageRegistry()
        assert reg.get("fizzbuzz-core", "9.9.9") is None

    def test_list_all_packages(self):
        reg = PackageRegistry()
        all_pkgs = reg.list_all()
        assert len(all_pkgs) == 8
        names = {p.name for p in all_pkgs}
        assert "fizzbuzz-core" in names
        assert "fizzbuzz-left-pad" in names
        assert "fizzbuzz-enterprise" in names

    def test_search_by_name(self):
        reg = PackageRegistry()
        results = reg.search("core")
        assert len(results) == 1
        assert results[0].name == "fizzbuzz-core"

    def test_search_partial_match(self):
        reg = PackageRegistry()
        results = reg.search("fizzbuzz")
        assert len(results) == 8  # All packages contain "fizzbuzz"

    def test_search_no_results(self):
        reg = PackageRegistry()
        results = reg.search("nonexistent-xyz")
        assert len(results) == 0

    def test_total_downloads(self):
        reg = PackageRegistry()
        assert reg.total_downloads > 0

    def test_left_pad_highest_downloads(self):
        """fizzbuzz-left-pad should have the most downloads (satirically)."""
        reg = PackageRegistry()
        pkg = reg.get("fizzbuzz-left-pad")
        assert pkg is not None
        all_pkgs = reg.list_all()
        max_downloads = max(p.download_count for p in all_pkgs)
        assert pkg.download_count == max_downloads

    def test_enterprise_has_all_dependencies(self):
        """fizzbuzz-enterprise@99.0.0 should depend on all other packages."""
        reg = PackageRegistry()
        pkg = reg.get("fizzbuzz-enterprise")
        assert pkg is not None
        assert len(pkg.dependencies) == 7  # All other packages

    def test_find_matching_versions(self):
        reg = PackageRegistry()
        matches = reg.find_matching_versions("fizzbuzz-core", "^1.0.0")
        assert len(matches) >= 1
        assert all(m.version.satisfies("^1.0.0") for m in matches)

    def test_get_all_versions(self):
        reg = PackageRegistry()
        versions = reg.get_all_versions("fizzbuzz-core")
        assert len(versions) >= 1


# ============================================================
# DPLL SAT Solver Tests
# ============================================================


class TestDPLLSolver:
    """Tests for the DPLL Boolean satisfiability solver."""

    def test_trivially_satisfiable(self):
        """Single positive literal: {x1}"""
        solver = DPLLSolver()
        result = solver.solve([[1]], 1)
        assert result.is_sat
        assert result.assignment.get(1) is True

    def test_trivially_unsatisfiable(self):
        """x1 AND NOT(x1) is UNSAT."""
        solver = DPLLSolver()
        result = solver.solve([[1], [-1]], 1)
        assert not result.is_sat

    def test_two_clauses_satisfiable(self):
        """(x1 OR x2) AND (NOT x1 OR x2) -- satisfiable by x2=True."""
        solver = DPLLSolver()
        result = solver.solve([[1, 2], [-1, 2]], 2)
        assert result.is_sat
        assert result.assignment.get(2) is True

    def test_unit_propagation(self):
        """Unit clause {x1} should force x1=True via propagation."""
        solver = DPLLSolver()
        result = solver.solve([[1], [1, 2], [-1, 2]], 2)
        assert result.is_sat
        assert result.assignment.get(1) is True

    def test_pure_literal_elimination(self):
        """If x1 appears only positively, set it to True."""
        solver = DPLLSolver()
        # x1 appears only positively, x2 appears both ways
        result = solver.solve([[1, 2], [1, -2]], 2)
        assert result.is_sat

    def test_three_variable_satisfiable(self):
        """(x1 OR x2) AND (NOT x2 OR x3) AND (NOT x1 OR NOT x3)"""
        solver = DPLLSolver()
        result = solver.solve([[1, 2], [-2, 3], [-1, -3]], 3)
        assert result.is_sat

    def test_pigeonhole_two_into_one(self):
        """2 pigeons into 1 hole: UNSAT.
        x1 = pigeon1 in hole1, x2 = pigeon2 in hole1
        At least one per pigeon: {x1}, {x2}
        At most one per hole: {-x1, -x2}
        """
        solver = DPLLSolver()
        result = solver.solve([[1], [2], [-1, -2]], 2)
        assert not result.is_sat

    def test_empty_clause_set(self):
        """No clauses -> trivially SAT."""
        solver = DPLLSolver()
        result = solver.solve([], 0)
        assert result.is_sat

    def test_empty_clause(self):
        """An empty clause is always false -> UNSAT."""
        solver = DPLLSolver()
        result = solver.solve([[]], 1)
        assert not result.is_sat

    def test_solver_stats_populated(self):
        """Solver should report statistics."""
        solver = DPLLSolver()
        result = solver.solve([[1, 2], [-1, 2], [1, -2]], 2)
        assert result.propagation_steps >= 0
        assert result.decisions >= 0
        assert result.backtracks >= 0

    def test_mutual_exclusion_clauses(self):
        """At most one of x1, x2, x3: pairwise negation."""
        solver = DPLLSolver()
        # At least one: (x1 OR x2 OR x3)
        # At most one: (-x1 OR -x2), (-x1 OR -x3), (-x2 OR -x3)
        clauses = [
            [1, 2, 3],
            [-1, -2],
            [-1, -3],
            [-2, -3],
        ]
        result = solver.solve(clauses, 3)
        assert result.is_sat
        # Exactly one should be true
        true_count = sum(1 for v in result.assignment.values() if v)
        assert true_count >= 1

    def test_implication_clause(self):
        """x1 -> x2 encoded as (-x1 OR x2). With x1=True, x2 must be True."""
        solver = DPLLSolver()
        result = solver.solve([[1], [-1, 2]], 2)
        assert result.is_sat
        assert result.assignment.get(1) is True
        assert result.assignment.get(2) is True

    def test_larger_instance(self):
        """5 variables, multiple constraints."""
        solver = DPLLSolver()
        clauses = [
            [1],           # x1 = True
            [-1, 2],       # x1 -> x2
            [-2, 3],       # x2 -> x3
            [-3, 4, 5],    # x3 -> (x4 OR x5)
            [-4, -5],      # NOT(x4 AND x5)
        ]
        result = solver.solve(clauses, 5)
        assert result.is_sat
        assert result.assignment.get(1) is True
        assert result.assignment.get(2) is True
        assert result.assignment.get(3) is True


# ============================================================
# Dependency Resolver Tests
# ============================================================


class TestDependencyResolver:
    """Tests for SAT-based dependency resolution."""

    def test_resolve_package_no_deps(self):
        reg = PackageRegistry()
        resolver = DependencyResolver(reg)
        result = resolver.resolve("fizzbuzz-core")
        assert len(result) == 1
        assert result[0].package.name == "fizzbuzz-core"

    def test_resolve_package_with_one_dep(self):
        reg = PackageRegistry()
        resolver = DependencyResolver(reg)
        result = resolver.resolve("fizzbuzz-ml")
        names = {r.package.name for r in result}
        assert "fizzbuzz-ml" in names
        assert "fizzbuzz-core" in names
        assert len(result) == 2

    def test_resolve_package_with_transitive_deps(self):
        """fizzbuzz-quantum depends on fizzbuzz-ml which depends on fizzbuzz-core."""
        reg = PackageRegistry()
        resolver = DependencyResolver(reg)
        result = resolver.resolve("fizzbuzz-quantum")
        names = {r.package.name for r in result}
        assert "fizzbuzz-quantum" in names
        assert "fizzbuzz-ml" in names
        assert "fizzbuzz-core" in names
        assert len(result) == 3

    def test_resolve_enterprise_all_packages(self):
        """fizzbuzz-enterprise depends on everything."""
        reg = PackageRegistry()
        resolver = DependencyResolver(reg)
        result = resolver.resolve("fizzbuzz-enterprise")
        assert len(result) == 8  # All packages

    def test_resolve_install_order(self):
        """Dependencies should come before dependents in install order."""
        reg = PackageRegistry()
        resolver = DependencyResolver(reg)
        result = resolver.resolve("fizzbuzz-ml")
        names = [r.package.name for r in result]
        core_idx = names.index("fizzbuzz-core")
        ml_idx = names.index("fizzbuzz-ml")
        assert core_idx < ml_idx

    def test_resolve_nonexistent_package(self):
        reg = PackageRegistry()
        resolver = DependencyResolver(reg)
        with pytest.raises(PackageNotFoundError):
            resolver.resolve("fizzbuzz-unicorn")

    def test_resolve_left_pad_no_deps(self):
        reg = PackageRegistry()
        resolver = DependencyResolver(reg)
        result = resolver.resolve("fizzbuzz-left-pad")
        assert len(result) == 1
        assert result[0].package.name == "fizzbuzz-left-pad"

    def test_solver_stats_after_resolve(self):
        reg = PackageRegistry()
        resolver = DependencyResolver(reg)
        resolver.resolve("fizzbuzz-enterprise")
        stats = resolver.get_solver_stats()
        assert stats["variables"] > 0

    def test_depth_computation(self):
        """Root packages should have depth 0, deps should have higher depth."""
        reg = PackageRegistry()
        resolver = DependencyResolver(reg)
        result = resolver.resolve("fizzbuzz-ml")
        depth_map = {r.package.name: r.depth for r in result}
        assert depth_map["fizzbuzz-core"] == 0
        assert depth_map["fizzbuzz-ml"] >= 1

    def test_required_by_tracking(self):
        """resolved deps should track who requires them."""
        reg = PackageRegistry()
        resolver = DependencyResolver(reg)
        result = resolver.resolve("fizzbuzz-ml")
        core_dep = next(r for r in result if r.package.name == "fizzbuzz-core")
        assert "fizzbuzz-ml" in core_dep.required_by


# ============================================================
# Lockfile Tests
# ============================================================


class TestLockfile:
    """Tests for deterministic lockfile generation."""

    def _make_resolved(self) -> list[ResolvedDependency]:
        """Helper to create resolved dependencies."""
        core = Package(name="fizzbuzz-core", version=SemVer(1, 0, 0))
        ml = Package(
            name="fizzbuzz-ml",
            version=SemVer(2, 1, 0),
            dependencies={"fizzbuzz-core": "^1.0.0"},
        )
        return [
            ResolvedDependency(package=core, depth=0, required_by=["fizzbuzz-ml"]),
            ResolvedDependency(package=ml, depth=1, required_by=[]),
        ]

    def test_generate_valid_json(self):
        lockfile = Lockfile()
        content = lockfile.generate(self._make_resolved())
        data = json.loads(content)
        assert "packages" in data
        assert "lockfile_version" in data

    def test_generate_pins_versions(self):
        lockfile = Lockfile()
        content = lockfile.generate(self._make_resolved())
        data = json.loads(content)
        assert data["packages"]["fizzbuzz-core"]["version"] == "1.0.0"
        assert data["packages"]["fizzbuzz-ml"]["version"] == "2.1.0"

    def test_generate_includes_integrity(self):
        lockfile = Lockfile()
        content = lockfile.generate(self._make_resolved())
        data = json.loads(content)
        for pkg_data in data["packages"].values():
            assert pkg_data["integrity"].startswith("sha256-")

    def test_generate_deterministic(self):
        """Same input should produce same output (except timestamp)."""
        resolved = self._make_resolved()
        lf1 = Lockfile()
        lf2 = Lockfile()
        content1 = lf1.generate(resolved)
        content2 = lf2.generate(resolved)
        data1 = json.loads(content1)
        data2 = json.loads(content2)
        # Compare packages (timestamps differ)
        assert data1["packages"] == data2["packages"]

    def test_verify_valid_lockfile(self):
        reg = PackageRegistry()
        resolver = DependencyResolver(reg)
        resolved = resolver.resolve("fizzbuzz-core")
        lockfile = Lockfile()
        content = lockfile.generate(resolved)
        violations = lockfile.verify(content, reg)
        assert len(violations) == 0

    def test_verify_corrupted_json(self):
        lockfile = Lockfile()
        violations = lockfile.verify("not json{{{", PackageRegistry())
        assert len(violations) == 1
        assert "not valid JSON" in violations[0]

    def test_package_count(self):
        lockfile = Lockfile()
        lockfile.generate(self._make_resolved())
        assert lockfile.package_count == 2

    def test_lockfile_includes_dependencies(self):
        lockfile = Lockfile()
        content = lockfile.generate(self._make_resolved())
        data = json.loads(content)
        ml_deps = data["packages"]["fizzbuzz-ml"]["dependencies"]
        assert "fizzbuzz-core" in ml_deps


# ============================================================
# Vulnerability Scanner Tests
# ============================================================


class TestVulnerabilityScanner:
    """Tests for the satirical vulnerability scanner."""

    def test_scanner_has_cves(self):
        scanner = VulnerabilityScanner()
        assert len(scanner._vulns) >= 3

    def test_audit_finds_left_pad_vuln(self):
        scanner = VulnerabilityScanner()
        pkg = Package(name="fizzbuzz-left-pad", version=SemVer(0, 0, 1))
        findings = scanner.audit([pkg])
        assert len(findings) >= 1
        assert any(v.cve_id == "CVE-2025-FIZZ-001" for v in findings)

    def test_audit_finds_ml_vuln(self):
        scanner = VulnerabilityScanner()
        pkg = Package(name="fizzbuzz-ml", version=SemVer(2, 1, 0))
        findings = scanner.audit([pkg])
        assert len(findings) >= 1
        assert any(v.cve_id == "CVE-2025-BUZZ-002" for v in findings)

    def test_audit_finds_enterprise_vuln(self):
        scanner = VulnerabilityScanner()
        pkg = Package(name="fizzbuzz-enterprise", version=SemVer(99, 0, 0))
        findings = scanner.audit([pkg])
        assert len(findings) >= 1
        assert any(v.cve_id == "CVE-2025-FB-003" for v in findings)

    def test_audit_no_findings_for_safe_package(self):
        scanner = VulnerabilityScanner()
        pkg = Package(name="fizzbuzz-core", version=SemVer(1, 0, 0))
        findings = scanner.audit([pkg])
        assert len(findings) == 0

    def test_severity_summary(self):
        scanner = VulnerabilityScanner()
        all_pkgs = PackageRegistry().list_all()
        findings = scanner.audit(all_pkgs)
        summary = scanner.get_severity_summary(findings)
        assert summary["CRITICAL"] >= 1

    def test_supply_chain_score_perfect(self):
        scanner = VulnerabilityScanner()
        assert scanner.get_supply_chain_score([]) == 100.0

    def test_supply_chain_score_degraded(self):
        scanner = VulnerabilityScanner()
        all_pkgs = PackageRegistry().list_all()
        findings = scanner.audit(all_pkgs)
        score = scanner.get_supply_chain_score(findings)
        assert 0.0 <= score < 100.0


# ============================================================
# FizzPM Manager Tests
# ============================================================


class TestFizzPMManager:
    """Tests for the FizzPM orchestrator."""

    def test_install_core(self):
        mgr = FizzPMManager()
        result = mgr.install("fizzbuzz-core")
        assert result["installed_count"] == 1
        assert result["package"] == "fizzbuzz-core"

    def test_install_enterprise_all_packages(self):
        mgr = FizzPMManager()
        result = mgr.install("fizzbuzz-enterprise")
        assert result["installed_count"] == 8

    def test_install_generates_lockfile(self):
        mgr = FizzPMManager()
        mgr.install("fizzbuzz-ml")
        assert mgr.lockfile_content is not None
        data = json.loads(mgr.lockfile_content)
        assert "packages" in data
        assert len(data["packages"]) == 2

    def test_install_runs_audit(self):
        mgr = FizzPMManager(audit_on_install=True)
        mgr.install("fizzbuzz-enterprise")
        assert len(mgr.vulnerabilities) > 0

    def test_install_skips_audit(self):
        mgr = FizzPMManager(audit_on_install=False)
        mgr.install("fizzbuzz-enterprise")
        assert len(mgr.vulnerabilities) == 0

    def test_install_nonexistent_raises(self):
        mgr = FizzPMManager()
        with pytest.raises(PackageNotFoundError):
            mgr.install("fizzbuzz-unicorn")

    def test_audit_all_packages(self):
        mgr = FizzPMManager()
        findings = mgr.audit()
        assert len(findings) > 0

    def test_audit_specific_packages(self):
        mgr = FizzPMManager()
        findings = mgr.audit(["fizzbuzz-core"])
        assert len(findings) == 0  # core has no vulns

    def test_list_packages(self):
        mgr = FizzPMManager()
        pkgs = mgr.list_packages()
        assert len(pkgs) == 8

    def test_search_packages(self):
        mgr = FizzPMManager()
        results = mgr.search("left-pad")
        assert len(results) == 1

    def test_render_install_summary(self):
        mgr = FizzPMManager()
        result = mgr.install("fizzbuzz-core")
        summary = mgr.render_install_summary(result)
        assert "fizzbuzz-core" in summary
        assert "SAT solver" in summary

    def test_render_audit_report(self):
        mgr = FizzPMManager()
        mgr.install("fizzbuzz-enterprise")
        report = mgr.render_audit_report()
        assert "Security Audit" in report
        assert "CVE" in report

    def test_render_dashboard(self):
        mgr = FizzPMManager()
        mgr.install("fizzbuzz-enterprise")
        dashboard = mgr.render_dashboard(width=60)
        assert "FizzPM" in dashboard
        assert "SAT Solver" in dashboard


# ============================================================
# FizzPM Dashboard Tests
# ============================================================


class TestFizzPMDashboard:
    """Tests for the ASCII dashboard rendering."""

    def test_render_empty(self):
        dashboard = FizzPMDashboard.render(
            installed=[],
            vulnerabilities=[],
            lockfile_content=None,
            registry=PackageRegistry(),
            solver_stats={"variables": 0, "propagation_steps": 0, "decisions": 0, "backtracks": 0},
        )
        assert "FizzPM" in dashboard
        assert "no packages installed" in dashboard

    def test_render_with_packages(self):
        mgr = FizzPMManager()
        mgr.install("fizzbuzz-ml")
        dashboard = FizzPMDashboard.render(
            installed=mgr.installed,
            vulnerabilities=mgr.vulnerabilities,
            lockfile_content=mgr.lockfile_content,
            registry=mgr.registry,
            solver_stats={"variables": 2, "propagation_steps": 1, "decisions": 0, "backtracks": 0},
        )
        assert "fizzbuzz-ml" in dashboard
        assert "fizzbuzz-core" in dashboard

    def test_render_with_lockfile(self):
        mgr = FizzPMManager()
        mgr.install("fizzbuzz-core")
        dashboard = FizzPMDashboard.render(
            installed=mgr.installed,
            vulnerabilities=[],
            lockfile_content=mgr.lockfile_content,
            registry=mgr.registry,
            solver_stats={"variables": 1, "propagation_steps": 0, "decisions": 0, "backtracks": 0},
        )
        assert "LOCKED" in dashboard

    def test_render_custom_width(self):
        dashboard = FizzPMDashboard.render(
            installed=[],
            vulnerabilities=[],
            lockfile_content=None,
            registry=PackageRegistry(),
            solver_stats={"variables": 0, "propagation_steps": 0, "decisions": 0, "backtracks": 0},
            width=80,
        )
        # Border should be 80 chars
        lines = dashboard.split("\n")
        assert any(len(line) == 80 for line in lines)


# ============================================================
# Exception Tests
# ============================================================


class TestPackageManagerExceptions:
    """Tests for the FizzPM exception hierarchy."""

    def test_base_exception(self):
        exc = PackageManagerError("test error")
        assert "EFP-PK00" in str(exc)

    def test_dependency_resolution_error(self):
        exc = DependencyResolutionError("fizzbuzz-core", "conflict detected")
        assert "EFP-PK10" in str(exc)
        assert exc.package == "fizzbuzz-core"
        assert exc.reason == "conflict detected"

    def test_package_not_found_error(self):
        exc = PackageNotFoundError("fizzbuzz-unicorn")
        assert "EFP-PK11" in str(exc)
        assert exc.package_name == "fizzbuzz-unicorn"

    def test_package_integrity_error(self):
        exc = PackageIntegrityError("test-pkg", "abc123", "def456")
        assert "EFP-PK12" in str(exc)
        assert exc.package_name == "test-pkg"

    def test_package_version_conflict_error(self):
        exc = PackageVersionConflictError("core", ["ml", "chaos"])
        assert "EFP-PK13" in str(exc)
        assert exc.package == "core"
        assert "diamond dependency" in str(exc)

    def test_exceptions_inherit_from_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        assert issubclass(PackageManagerError, FizzBuzzError)
        assert issubclass(DependencyResolutionError, PackageManagerError)
        assert issubclass(PackageNotFoundError, PackageManagerError)
        assert issubclass(PackageIntegrityError, PackageManagerError)
        assert issubclass(PackageVersionConflictError, PackageManagerError)
