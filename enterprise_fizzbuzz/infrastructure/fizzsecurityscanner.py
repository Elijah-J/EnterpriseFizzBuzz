"""
Enterprise FizzBuzz Platform - FizzSecurityScanner: SAST/DAST Security Scanner

Static and dynamic security scanning for FizzLang code and infrastructure.
Detects SQL injection, XSS, command injection, hardcoded secrets, eval usage,
dependency vulnerabilities, and leaked credentials.

Architecture reference: SonarQube, Snyk, Semgrep, Bandit, OWASP ZAP.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzsecurityscanner import (
    FizzSecurityScannerError, FizzSecurityScannerSASTError,
    FizzSecurityScannerDASTError, FizzSecurityScannerDependencyError,
    FizzSecurityScannerSecretError, FizzSecurityScannerConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzsecurityscanner")

EVENT_SEC_FINDING = EventType.register("FIZZSECURITYSCANNER_FINDING")

FIZZSECURITYSCANNER_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 170


class ScanType(Enum):
    SAST = "sast"
    DAST = "dast"
    DEPENDENCY = "dependency"
    SECRET = "secret"

class Severity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

class FindingStatus(Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


@dataclass
class FizzSecurityScannerConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class Finding:
    finding_id: str = ""
    scan_type: ScanType = ScanType.SAST
    severity: Severity = Severity.MEDIUM
    title: str = ""
    description: str = ""
    file_path: str = ""
    line_number: int = 0
    status: FindingStatus = FindingStatus.OPEN
    cwe_id: str = ""

@dataclass
class ScanResult:
    scan_id: str = ""
    scan_type: ScanType = ScanType.SAST
    findings: List[Finding] = field(default_factory=list)
    scanned_files: int = 0
    duration_ms: float = 0.0
    passed: bool = True


# SAST patterns
SAST_RULES = [
    (r'\beval\s*\(', "Use of eval()", Severity.HIGH, "CWE-95"),
    (r'\bexec\s*\(', "Use of exec()", Severity.HIGH, "CWE-95"),
    (r'\bos\.system\s*\(', "Command injection via os.system()", Severity.CRITICAL, "CWE-78"),
    (r'\bsubprocess\.call\s*\(', "Command injection via subprocess", Severity.HIGH, "CWE-78"),
    (r'\bos\.popen\s*\(', "Command injection via os.popen()", Severity.HIGH, "CWE-78"),
    (r'SELECT\s+.*\s+FROM\s+.*\s+WHERE\s+.*\+', "Potential SQL injection", Severity.CRITICAL, "CWE-89"),
    (r'\.innerHTML\s*=', "Potential XSS via innerHTML", Severity.HIGH, "CWE-79"),
    (r'__import__\s*\(', "Dynamic import", Severity.MEDIUM, "CWE-502"),
]

SECRET_PATTERNS = [
    (r'(?i)api[_-]?key\s*[=:]\s*["\'][\w-]{16,}', "Hardcoded API key", Severity.HIGH),
    (r'(?i)password\s*[=:]\s*["\'][^"\']{4,}', "Hardcoded password", Severity.CRITICAL),
    (r'(?i)secret\s*[=:]\s*["\'][^"\']{8,}', "Hardcoded secret", Severity.HIGH),
    (r'(?i)token\s*[=:]\s*["\'][^"\']{16,}', "Hardcoded token", Severity.HIGH),
    (r'AKIA[A-Z0-9]{16}', "AWS Access Key ID", Severity.CRITICAL),
    (r'ghp_[A-Za-z0-9]{36}', "GitHub Personal Access Token", Severity.CRITICAL),
]

KNOWN_VULNERABLE_DEPS = {
    "requests": {"2.25.0": "CVE-2023-32681", "2.24.0": "CVE-2023-32681", "2.19.0": "CVE-2018-18074"},
    "urllib3": {"1.24.0": "CVE-2019-11324", "1.25.0": "CVE-2019-11236"},
    "flask": {"1.0": "CVE-2023-30861"},
    "django": {"2.2": "CVE-2023-36053"},
    "pyyaml": {"5.3": "CVE-2020-14343"},
}


class SASTScanner:
    """Static Application Security Testing scanner."""

    def scan(self, code: str, filename: str = "input.py") -> ScanResult:
        start = time.time()
        findings = []
        for line_num, line in enumerate(code.split("\n"), 1):
            for pattern, title, severity, cwe in SAST_RULES:
                if re.search(pattern, line):
                    findings.append(Finding(
                        finding_id=f"sast-{uuid.uuid4().hex[:8]}",
                        scan_type=ScanType.SAST,
                        severity=severity,
                        title=title,
                        description=f"Pattern matched on line {line_num}: {line.strip()[:80]}",
                        file_path=filename,
                        line_number=line_num,
                        cwe_id=cwe,
                    ))
        return ScanResult(
            scan_id=f"scan-{uuid.uuid4().hex[:8]}",
            scan_type=ScanType.SAST,
            findings=findings,
            scanned_files=1,
            duration_ms=(time.time() - start) * 1000,
            passed=len(findings) == 0,
        )


class DASTScanner:
    """Dynamic Application Security Testing scanner."""

    def scan(self, url: str, headers: Optional[Dict[str, str]] = None) -> ScanResult:
        start = time.time()
        findings = []
        # Simulate DAST checks
        if url.startswith("http://") and not url.startswith("http://localhost"):
            findings.append(Finding(
                finding_id=f"dast-{uuid.uuid4().hex[:8]}",
                scan_type=ScanType.DAST,
                severity=Severity.MEDIUM,
                title="Insecure HTTP connection",
                description=f"URL {url} uses unencrypted HTTP",
                file_path=url,
                cwe_id="CWE-319",
            ))
        if not headers or "Authorization" not in headers:
            findings.append(Finding(
                finding_id=f"dast-{uuid.uuid4().hex[:8]}",
                scan_type=ScanType.DAST,
                severity=Severity.LOW,
                title="Missing authentication header",
                description="No Authorization header provided",
                file_path=url,
                cwe_id="CWE-306",
            ))
        return ScanResult(
            scan_id=f"scan-{uuid.uuid4().hex[:8]}",
            scan_type=ScanType.DAST,
            findings=findings,
            scanned_files=1,
            duration_ms=(time.time() - start) * 1000,
            passed=len(findings) == 0,
        )


class DependencyScanner:
    """Dependency vulnerability scanner."""

    def scan(self, dependencies: Dict[str, str]) -> ScanResult:
        start = time.time()
        findings = []
        for pkg, version in dependencies.items():
            vulns = KNOWN_VULNERABLE_DEPS.get(pkg, {})
            cve = vulns.get(version)
            if cve:
                findings.append(Finding(
                    finding_id=f"dep-{uuid.uuid4().hex[:8]}",
                    scan_type=ScanType.DEPENDENCY,
                    severity=Severity.HIGH,
                    title=f"Vulnerable dependency: {pkg}=={version}",
                    description=f"{cve} affects {pkg} {version}",
                    file_path="requirements.txt",
                    cwe_id=cve,
                ))
        return ScanResult(
            scan_id=f"scan-{uuid.uuid4().hex[:8]}",
            scan_type=ScanType.DEPENDENCY,
            findings=findings,
            scanned_files=1,
            duration_ms=(time.time() - start) * 1000,
            passed=len(findings) == 0,
        )


class SecretScanner:
    """Secret detection scanner."""

    def scan(self, code: str) -> ScanResult:
        start = time.time()
        findings = []
        for line_num, line in enumerate(code.split("\n"), 1):
            for pattern, title, severity in SECRET_PATTERNS:
                if re.search(pattern, line):
                    findings.append(Finding(
                        finding_id=f"secret-{uuid.uuid4().hex[:8]}",
                        scan_type=ScanType.SECRET,
                        severity=severity,
                        title=title,
                        description=f"Secret detected on line {line_num}",
                        file_path="<input>",
                        line_number=line_num,
                        cwe_id="CWE-798",
                    ))
        return ScanResult(
            scan_id=f"scan-{uuid.uuid4().hex[:8]}",
            scan_type=ScanType.SECRET,
            findings=findings,
            scanned_files=1,
            duration_ms=(time.time() - start) * 1000,
            passed=len(findings) == 0,
        )


class FizzSecurityScannerDashboard:
    def __init__(self, sast: Optional[SASTScanner] = None, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._sast = sast; self._width = width
    def render(self) -> str:
        lines = ["=" * self._width, "FizzSecurityScanner Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZSECURITYSCANNER_VERSION}",
                 "  Scanners: SAST, DAST, Dependency, Secret",
                 f"  SAST Rules: {len(SAST_RULES)}", f"  Secret Patterns: {len(SECRET_PATTERNS)}",
                 f"  Known Vulnerable Deps: {sum(len(v) for v in KNOWN_VULNERABLE_DEPS.values())}"]
        return "\n".join(lines)


class FizzSecurityScannerMiddleware(IMiddleware):
    def __init__(self, sast: Optional[SASTScanner] = None, dashboard: Optional[FizzSecurityScannerDashboard] = None) -> None:
        self._sast = sast; self._dashboard = dashboard
    def get_name(self) -> str: return "fizzsecurityscanner"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY
    def process(self, context: Any, next_handler: Any) -> Any:
        if next_handler: return next_handler(context)
        return context
    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzsecurityscanner_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[SASTScanner, FizzSecurityScannerDashboard, FizzSecurityScannerMiddleware]:
    sast = SASTScanner()
    dashboard = FizzSecurityScannerDashboard(sast, dashboard_width)
    middleware = FizzSecurityScannerMiddleware(sast, dashboard)
    logger.info("FizzSecurityScanner initialized: %d SAST rules, %d secret patterns",
                len(SAST_RULES), len(SECRET_PATTERNS))
    return sast, dashboard, middleware
