"""
Enterprise FizzBuzz Platform - FizzSecurityScanner SAST/DAST Security Scanner Tests

Comprehensive test suite for the FizzSecurityScanner subsystem, which provides
static application security testing (SAST), dynamic application security testing
(DAST), dependency vulnerability scanning, and secret detection for FizzLang code
and infrastructure. In a platform where FizzBuzz computation underpins mission-
critical business logic, a single SQL injection or leaked API key in the FizzLang
codebase could compromise the integrity of every divisibility result ever produced.
These tests define the behavioral contract that all scanner implementations must
honor.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizzsecurityscanner import (
    FIZZSECURITYSCANNER_VERSION,
    MIDDLEWARE_PRIORITY,
    ScanType,
    Severity,
    FindingStatus,
    FizzSecurityScannerConfig,
    Finding,
    ScanResult,
    SASTScanner,
    DASTScanner,
    DependencyScanner,
    SecretScanner,
    FizzSecurityScannerDashboard,
    FizzSecurityScannerMiddleware,
    create_fizzsecurityscanner_subsystem,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singleton state between tests."""
    _SingletonMeta.reset()


@pytest.fixture
def sast_scanner():
    """Provide a fresh SASTScanner for each test."""
    return SASTScanner()


@pytest.fixture
def secret_scanner():
    """Provide a fresh SecretScanner for each test."""
    return SecretScanner()


@pytest.fixture
def dast_scanner():
    """Provide a fresh DASTScanner for each test."""
    return DASTScanner()


@pytest.fixture
def dependency_scanner():
    """Provide a fresh DependencyScanner for each test."""
    return DependencyScanner()


# ---------------------------------------------------------------------------
# TestConstants
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify module-level constants are correctly defined."""

    def test_version(self):
        assert FIZZSECURITYSCANNER_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 170


# ---------------------------------------------------------------------------
# TestSASTScanner
# ---------------------------------------------------------------------------

class TestSASTScanner:
    """Validate that the SASTScanner detects real vulnerability patterns in code."""

    def test_clean_code_passes(self, sast_scanner):
        """Safe code with no vulnerability patterns should yield zero findings."""
        clean_code = "def fizzbuzz(n):\n    if n % 15 == 0:\n        return 'FizzBuzz'\n    return str(n)\n"
        result = sast_scanner.scan(clean_code, "fizzbuzz.py")
        assert isinstance(result, ScanResult)
        assert result.scan_type == ScanType.SAST
        assert result.passed is True
        assert len(result.findings) == 0

    def test_eval_detected(self, sast_scanner):
        """Use of eval() is a critical code injection vector and must be flagged."""
        dangerous_code = "result = eval(user_input)\n"
        result = sast_scanner.scan(dangerous_code, "handler.py")
        assert result.passed is False
        assert len(result.findings) > 0
        severities = [f.severity for f in result.findings]
        titles = [f.title.lower() for f in result.findings]
        assert any("eval" in t for t in titles), f"Expected eval finding, got titles: {titles}"
        assert any(s in (Severity.CRITICAL, Severity.HIGH) for s in severities)

    def test_sql_injection_detected(self, sast_scanner):
        """String-formatted SQL queries must be flagged as injection risks."""
        sqli_code = 'query = "SELECT * FROM users WHERE id = " + user_id\ncursor.execute(query)\n'
        result = sast_scanner.scan(sqli_code, "db.py")
        assert result.passed is False
        assert len(result.findings) > 0
        titles = [f.title.lower() for f in result.findings]
        assert any("sql" in t or "injection" in t for t in titles), (
            f"Expected SQL injection finding, got: {titles}"
        )

    def test_command_injection_detected(self, sast_scanner):
        """os.system() calls must be flagged as command injection risks."""
        cmd_code = 'import os\nos.system("rm -rf " + user_path)\n'
        result = sast_scanner.scan(cmd_code, "cleanup.py")
        assert result.passed is False
        assert len(result.findings) > 0
        titles = [f.title.lower() for f in result.findings]
        assert any("command" in t or "os.system" in t or "injection" in t for t in titles), (
            f"Expected command injection finding, got: {titles}"
        )


# ---------------------------------------------------------------------------
# TestSecretScanner
# ---------------------------------------------------------------------------

class TestSecretScanner:
    """Validate that the SecretScanner detects hardcoded credentials in source."""

    def test_clean_code_passes(self, secret_scanner):
        """Code without secrets should produce zero findings."""
        clean_code = "def get_config():\n    return {'timeout': 30}\n"
        result = secret_scanner.scan(clean_code)
        assert isinstance(result, ScanResult)
        assert result.scan_type == ScanType.SECRET
        assert result.passed is True
        assert len(result.findings) == 0

    def test_api_key_detected(self, secret_scanner):
        """Hardcoded API keys must be flagged regardless of variable naming."""
        code_with_key = 'API_KEY = "sk-proj-abc123def456ghi789jkl012mno345pqr678"\n'
        result = secret_scanner.scan(code_with_key)
        assert result.passed is False
        assert len(result.findings) > 0
        titles = [f.title.lower() for f in result.findings]
        assert any("key" in t or "secret" in t or "credential" in t or "token" in t for t in titles), (
            f"Expected API key finding, got: {titles}"
        )

    def test_password_detected(self, secret_scanner):
        """Hardcoded password assignments must be flagged."""
        code_with_pw = 'password = "SuperSecret123!"\ndb_password = "hunter2"\n'
        result = secret_scanner.scan(code_with_pw)
        assert result.passed is False
        assert len(result.findings) > 0
        titles = [f.title.lower() for f in result.findings]
        assert any("password" in t or "secret" in t or "credential" in t for t in titles), (
            f"Expected password finding, got: {titles}"
        )


# ---------------------------------------------------------------------------
# TestDASTScanner
# ---------------------------------------------------------------------------

class TestDASTScanner:
    """Validate that the DASTScanner simulates dynamic vulnerability detection."""

    def test_scan_returns_result(self, dast_scanner):
        """A DAST scan against any URL must return a well-formed ScanResult."""
        result = dast_scanner.scan("https://fizzbuzz.internal/api/v1/health", {})
        assert isinstance(result, ScanResult)
        assert result.scan_type == ScanType.DAST
        assert isinstance(result.findings, list)
        assert result.duration_ms >= 0

    def test_insecure_url_findings(self, dast_scanner):
        """HTTP (non-TLS) endpoints must be flagged as insecure transport."""
        result = dast_scanner.scan("http://fizzbuzz.internal/api/v1/evaluate", {})
        assert len(result.findings) > 0
        titles = [f.title.lower() for f in result.findings]
        assert any(
            "http" in t or "tls" in t or "ssl" in t or "insecure" in t or "transport" in t
            for t in titles
        ), f"Expected insecure transport finding, got: {titles}"


# ---------------------------------------------------------------------------
# TestDependencyScanner
# ---------------------------------------------------------------------------

class TestDependencyScanner:
    """Validate that the DependencyScanner flags known vulnerable packages."""

    def test_clean_dependencies_pass(self, dependency_scanner):
        """A set of up-to-date, safe dependencies should pass cleanly."""
        deps = {"requests": "2.31.0", "pytest": "7.4.0"}
        result = dependency_scanner.scan(deps)
        assert isinstance(result, ScanResult)
        assert result.scan_type == ScanType.DEPENDENCY
        assert result.passed is True

    def test_known_vulnerable_version_detected(self, dependency_scanner):
        """Dependencies with known CVEs must be flagged by version analysis."""
        deps = {"requests": "2.19.0", "urllib3": "1.24.0"}
        result = dependency_scanner.scan(deps)
        assert result.passed is False
        assert len(result.findings) > 0
        finding_descs = [f.description.lower() for f in result.findings]
        assert any(
            "vulnerab" in d or "cve" in d or "outdated" in d or "insecure" in d
            for d in finding_descs
        ), f"Expected vulnerability description, got: {finding_descs}"


# ---------------------------------------------------------------------------
# TestFinding
# ---------------------------------------------------------------------------

class TestFinding:
    """Verify the Finding dataclass structure and enum integration."""

    def test_dataclass_fields(self):
        """Finding must expose all required fields with correct types."""
        finding = Finding(
            finding_id="FIZZSEC-001",
            scan_type=ScanType.SAST,
            severity=Severity.HIGH,
            title="Eval Usage Detected",
            description="Use of eval() allows arbitrary code execution.",
            file_path="handler.py",
            line_number=42,
            status=FindingStatus.OPEN,
            cwe_id="CWE-95",
        )
        assert finding.finding_id == "FIZZSEC-001"
        assert finding.scan_type == ScanType.SAST
        assert finding.severity == Severity.HIGH
        assert finding.title == "Eval Usage Detected"
        assert finding.file_path == "handler.py"
        assert finding.line_number == 42
        assert finding.status == FindingStatus.OPEN
        assert finding.cwe_id == "CWE-95"

    def test_severity_levels(self):
        """All five severity levels must be present in the enum."""
        assert Severity.CRITICAL is not None
        assert Severity.HIGH is not None
        assert Severity.MEDIUM is not None
        assert Severity.LOW is not None
        assert Severity.INFO is not None
        assert len(Severity) == 5


# ---------------------------------------------------------------------------
# TestFizzSecurityScannerDashboard
# ---------------------------------------------------------------------------

class TestFizzSecurityScannerDashboard:
    """Validate the security dashboard rendering contract."""

    def test_render_returns_string(self):
        """The dashboard must produce a non-empty string representation."""
        dashboard = FizzSecurityScannerDashboard()
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_security_info(self):
        """The rendered dashboard must reference security scanning context."""
        dashboard = FizzSecurityScannerDashboard()
        output = dashboard.render().lower()
        assert any(
            keyword in output
            for keyword in ("security", "scanner", "scan", "fizzsecurityscanner", "vulnerability")
        ), f"Dashboard output missing security context: {output[:200]}"


# ---------------------------------------------------------------------------
# TestFizzSecurityScannerMiddleware
# ---------------------------------------------------------------------------

class TestFizzSecurityScannerMiddleware:
    """Validate middleware integration contract for the security scanner."""

    def test_name(self):
        """Middleware must identify itself as 'fizzsecurityscanner'."""
        mw = FizzSecurityScannerMiddleware()
        assert mw.get_name() == "fizzsecurityscanner"

    def test_priority(self):
        """Middleware priority must match the module constant."""
        mw = FizzSecurityScannerMiddleware()
        assert mw.get_priority() == 170

    def test_process_calls_next(self):
        """Middleware must invoke the next handler in the pipeline."""
        mw = FizzSecurityScannerMiddleware()
        ctx = ProcessingContext(number=15, session_id="test")
        mock_next = MagicMock(return_value=ctx)
        result = mw.process(ctx, mock_next)
        mock_next.assert_called_once()
        assert isinstance(result, ProcessingContext)


# ---------------------------------------------------------------------------
# TestCreateSubsystem
# ---------------------------------------------------------------------------

class TestCreateSubsystem:
    """Validate the factory function that wires the subsystem together."""

    def test_returns_tuple(self):
        """Factory must return a 3-tuple of (scanner, dashboard, middleware)."""
        result = create_fizzsecurityscanner_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_scanner_works(self):
        """The scanner returned by the factory must be functional."""
        scanner, _, _ = create_fizzsecurityscanner_subsystem()
        assert isinstance(scanner, SASTScanner)
        result = scanner.scan("x = 1\n", "safe.py")
        assert isinstance(result, ScanResult)

    def test_can_scan_fizzbuzz_code(self):
        """The scanner must handle representative FizzBuzz application code."""
        scanner, _, _ = create_fizzsecurityscanner_subsystem()
        fizzbuzz_code = (
            "def fizzbuzz(n: int) -> str:\n"
            "    if n % 15 == 0:\n"
            "        return 'FizzBuzz'\n"
            "    elif n % 3 == 0:\n"
            "        return 'Fizz'\n"
            "    elif n % 5 == 0:\n"
            "        return 'Buzz'\n"
            "    return str(n)\n"
        )
        result = scanner.scan(fizzbuzz_code, "core_engine.py")
        assert result.passed is True
        assert result.scanned_files >= 1
