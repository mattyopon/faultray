# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""End-of-Life (EOL) checker for middleware and runtime versions.

Detects outdated or EOL software from APM agent process data and
flags them as infrastructure risks in simulation reports.

Data sources:
- APM agent process list (name, cmdline → detect version)
- Known EOL dates database (built-in, no external API needed)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# EOL Database — known software lifecycle dates
# Sources: endoflife.date, official vendor announcements
# Last updated: 2026-03-31
# ---------------------------------------------------------------------------

@dataclass
class SoftwareLifecycle:
    """Lifecycle entry for a specific software version."""
    name: str
    version: str
    release_date: str  # YYYY-MM-DD
    eol_date: str  # YYYY-MM-DD or "active"
    lts: bool = False
    severity: str = "warning"  # "critical" if already EOL, "warning" if approaching


# Major software EOL database
EOL_DATABASE: list[SoftwareLifecycle] = [
    # --- Python ---
    SoftwareLifecycle("Python", "3.8", "2019-10-14", "2024-10-07"),
    SoftwareLifecycle("Python", "3.9", "2020-10-05", "2025-10-05"),
    SoftwareLifecycle("Python", "3.10", "2021-10-04", "2026-10-04"),
    SoftwareLifecycle("Python", "3.11", "2022-10-24", "2027-10-24"),
    SoftwareLifecycle("Python", "3.12", "2023-10-02", "2028-10-02"),
    SoftwareLifecycle("Python", "3.13", "2024-10-07", "2029-10-07"),

    # --- Node.js ---
    SoftwareLifecycle("Node.js", "16", "2021-04-20", "2023-09-11"),
    SoftwareLifecycle("Node.js", "18", "2022-04-19", "2025-04-30", lts=True),
    SoftwareLifecycle("Node.js", "20", "2023-04-18", "2026-04-30", lts=True),
    SoftwareLifecycle("Node.js", "22", "2024-04-24", "2027-04-30", lts=True),

    # --- Java / JDK ---
    SoftwareLifecycle("Java", "8", "2014-03-18", "2030-12-31", lts=True),  # Extended support
    SoftwareLifecycle("Java", "11", "2018-09-25", "2026-09-30", lts=True),
    SoftwareLifecycle("Java", "17", "2021-09-14", "2029-09-30", lts=True),
    SoftwareLifecycle("Java", "21", "2023-09-19", "2031-09-30", lts=True),

    # --- PostgreSQL ---
    SoftwareLifecycle("PostgreSQL", "12", "2019-10-03", "2024-11-14"),
    SoftwareLifecycle("PostgreSQL", "13", "2020-09-24", "2025-11-13"),
    SoftwareLifecycle("PostgreSQL", "14", "2021-09-30", "2026-11-12"),
    SoftwareLifecycle("PostgreSQL", "15", "2022-10-13", "2027-11-11"),
    SoftwareLifecycle("PostgreSQL", "16", "2023-09-14", "2028-11-09"),
    SoftwareLifecycle("PostgreSQL", "17", "2024-09-26", "2029-11-08"),

    # --- MySQL ---
    SoftwareLifecycle("MySQL", "5.7", "2015-10-21", "2023-10-21"),
    SoftwareLifecycle("MySQL", "8.0", "2018-04-19", "2026-04-30"),
    SoftwareLifecycle("MySQL", "8.4", "2024-04-30", "2032-04-30", lts=True),

    # --- Redis ---
    SoftwareLifecycle("Redis", "6", "2020-04-30", "2024-10-31"),
    SoftwareLifecycle("Redis", "7.0", "2022-04-27", "2025-07-31"),
    SoftwareLifecycle("Redis", "7.2", "2023-08-15", "2026-08-31"),
    SoftwareLifecycle("Redis", "7.4", "2024-07-22", "2027-07-31"),

    # --- Nginx ---
    SoftwareLifecycle("Nginx", "1.24", "2023-04-11", "2024-04-30"),
    SoftwareLifecycle("Nginx", "1.26", "2024-04-23", "2025-04-30"),
    SoftwareLifecycle("Nginx", "1.27", "2024-06-04", "active"),

    # --- MongoDB ---
    SoftwareLifecycle("MongoDB", "5.0", "2021-07-13", "2024-10-31"),
    SoftwareLifecycle("MongoDB", "6.0", "2022-07-19", "2025-07-31"),
    SoftwareLifecycle("MongoDB", "7.0", "2023-08-08", "2026-08-31"),

    # --- Ubuntu ---
    SoftwareLifecycle("Ubuntu", "20.04", "2020-04-23", "2025-04-02", lts=True),
    SoftwareLifecycle("Ubuntu", "22.04", "2022-04-21", "2027-04-01", lts=True),
    SoftwareLifecycle("Ubuntu", "24.04", "2024-04-25", "2029-04-01", lts=True),

    # --- Debian ---
    SoftwareLifecycle("Debian", "10", "2019-07-06", "2024-06-30"),
    SoftwareLifecycle("Debian", "11", "2021-08-14", "2026-06-30"),
    SoftwareLifecycle("Debian", "12", "2023-06-10", "2028-06-30"),

    # --- CentOS / RHEL ---
    SoftwareLifecycle("CentOS", "7", "2014-07-07", "2024-06-30"),
    SoftwareLifecycle("CentOS", "8", "2019-09-24", "2021-12-31"),
    SoftwareLifecycle("RHEL", "8", "2019-05-07", "2029-05-31"),
    SoftwareLifecycle("RHEL", "9", "2022-05-17", "2032-05-31"),

    # --- Kubernetes ---
    SoftwareLifecycle("Kubernetes", "1.27", "2023-04-11", "2024-06-28"),
    SoftwareLifecycle("Kubernetes", "1.28", "2023-08-15", "2024-10-28"),
    SoftwareLifecycle("Kubernetes", "1.29", "2023-12-13", "2025-02-28"),
    SoftwareLifecycle("Kubernetes", "1.30", "2024-04-17", "2025-06-28"),
    SoftwareLifecycle("Kubernetes", "1.31", "2024-08-13", "2025-10-28"),
    SoftwareLifecycle("Kubernetes", "1.32", "2024-12-11", "2026-02-28"),

    # --- Elasticsearch ---
    SoftwareLifecycle("Elasticsearch", "7", "2019-04-10", "2025-08-01"),
    SoftwareLifecycle("Elasticsearch", "8", "2022-02-10", "2026-08-01"),

    # --- Apache HTTP ---
    SoftwareLifecycle("Apache", "2.4", "2012-02-21", "active"),

    # --- RabbitMQ ---
    SoftwareLifecycle("RabbitMQ", "3.12", "2023-06-01", "2024-12-31"),
    SoftwareLifecycle("RabbitMQ", "3.13", "2024-02-22", "2025-12-31"),
    SoftwareLifecycle("RabbitMQ", "4.0", "2024-10-08", "2026-07-31"),

    # --- Kafka ---
    SoftwareLifecycle("Kafka", "3.6", "2023-10-12", "2024-10-31"),
    SoftwareLifecycle("Kafka", "3.7", "2024-02-27", "2025-02-28"),
    SoftwareLifecycle("Kafka", "3.8", "2024-07-23", "2025-07-31"),
]


# ---------------------------------------------------------------------------
# Version detection from process info
# ---------------------------------------------------------------------------

# Patterns to detect software + version from process name/cmdline
_DETECT_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    # (software_name, source, regex_pattern)
    ("Python", "cmdline", re.compile(r"python(\d+\.\d+)")),
    ("Python", "cmdline", re.compile(r"Python\s+(\d+\.\d+)")),
    ("Node.js", "cmdline", re.compile(r"node.*?v?(\d+)\.")),
    ("Node.js", "name", re.compile(r"node(\d+)")),
    ("Java", "cmdline", re.compile(r"java.*?version.*?(\d+)")),
    ("Java", "cmdline", re.compile(r"-Djava\.version=(\d+)")),
    ("PostgreSQL", "name", re.compile(r"postgres.*?(\d+)")),
    ("PostgreSQL", "cmdline", re.compile(r"postgresql.*?(\d+)")),
    ("MySQL", "name", re.compile(r"mysql.*?(\d+\.\d+)")),
    ("MySQL", "cmdline", re.compile(r"mysqld.*?(\d+\.\d+)")),
    ("Redis", "name", re.compile(r"redis.*?(\d+\.\d+)")),
    ("Redis", "cmdline", re.compile(r"redis-server.*?(\d+\.\d+)")),
    ("Nginx", "name", re.compile(r"nginx")),
    ("Nginx", "cmdline", re.compile(r"nginx.*?(\d+\.\d+)")),
    ("MongoDB", "name", re.compile(r"mongod")),
    ("MongoDB", "cmdline", re.compile(r"mongod.*?(\d+\.\d+)")),
    ("Elasticsearch", "name", re.compile(r"elasticsearch")),
    ("Elasticsearch", "cmdline", re.compile(r"elasticsearch.*?(\d+)")),
    ("RabbitMQ", "name", re.compile(r"rabbit")),
    ("RabbitMQ", "cmdline", re.compile(r"rabbitmq.*?(\d+\.\d+)")),
    ("Kafka", "name", re.compile(r"kafka")),
    ("Kafka", "cmdline", re.compile(r"kafka.*?(\d+\.\d+)")),
]


@dataclass
class DetectedSoftware:
    """Software detected from a running process."""
    name: str
    version: str
    source: str  # "process", "os_info", "manual"
    process_name: str = ""
    pid: int = 0


@dataclass
class EOLWarning:
    """Warning about EOL or approaching-EOL software."""
    software: str
    version: str
    eol_date: str
    days_until_eol: int  # negative = already expired
    status: str  # "eol", "approaching", "ok"
    severity: str  # "critical", "warning", "info"
    recommendation: str
    risk_score: float  # 0-10
    source: str  # how it was detected


@dataclass
class EOLReport:
    """Full EOL check report."""
    checked_at: str
    software_detected: list[DetectedSoftware] = field(default_factory=list)
    warnings: list[EOLWarning] = field(default_factory=list)
    critical_count: int = 0
    warning_count: int = 0
    ok_count: int = 0


# ---------------------------------------------------------------------------
# EOL Checker
# ---------------------------------------------------------------------------

class EOLChecker:
    """Checks detected software versions against the EOL database."""

    def __init__(self, today: date | None = None) -> None:
        self.today = today or date.today()
        self._db = {(e.name, e.version): e for e in EOL_DATABASE}

    def detect_from_processes(
        self, processes: list[dict[str, str]]
    ) -> list[DetectedSoftware]:
        """Detect software versions from process list.

        Each process dict should have 'name', 'cmdline', and optionally 'pid'.
        """
        detected: list[DetectedSoftware] = []
        seen: set[tuple[str, str]] = set()

        for proc in processes:
            proc_name = proc.get("name", "")
            cmdline = proc.get("cmdline", "")
            pid = int(proc.get("pid", 0))

            for sw_name, source, pattern in _DETECT_PATTERNS:
                text = proc_name if source == "name" else cmdline
                match = pattern.search(text)
                if match:
                    version = match.group(1) if match.lastindex else ""
                    key = (sw_name, version)
                    if key not in seen and version:
                        seen.add(key)
                        detected.append(DetectedSoftware(
                            name=sw_name,
                            version=version,
                            source="process",
                            process_name=proc_name,
                            pid=pid,
                        ))

        return detected

    def detect_from_os_info(self, os_info: str) -> list[DetectedSoftware]:
        """Detect OS version from os_info string (e.g., 'Ubuntu 22.04')."""
        detected: list[DetectedSoftware] = []

        os_patterns = [
            ("Ubuntu", re.compile(r"Ubuntu\s+(\d+\.\d+)")),
            ("Debian", re.compile(r"Debian\s+(\d+)")),
            ("CentOS", re.compile(r"CentOS.*?(\d+)")),
            ("RHEL", re.compile(r"(?:RHEL|Red Hat).*?(\d+)")),
        ]

        for name, pattern in os_patterns:
            match = pattern.search(os_info)
            if match:
                detected.append(DetectedSoftware(
                    name=name,
                    version=match.group(1),
                    source="os_info",
                ))

        return detected

    def check(self, detected: list[DetectedSoftware]) -> EOLReport:
        """Check detected software against EOL database and generate report."""
        report = EOLReport(
            checked_at=datetime.now(timezone.utc).isoformat(),
            software_detected=detected,
        )

        for sw in detected:
            warning = self._check_one(sw)
            if warning:
                report.warnings.append(warning)
                if warning.status == "eol":
                    report.critical_count += 1
                elif warning.status == "approaching":
                    report.warning_count += 1
                else:
                    report.ok_count += 1
            else:
                report.ok_count += 1

        # Sort: critical first, then by days_until_eol
        report.warnings.sort(key=lambda w: (
            0 if w.severity == "critical" else 1 if w.severity == "warning" else 2,
            w.days_until_eol,
        ))

        return report

    def check_all_known(self) -> EOLReport:
        """Check ALL software in the EOL database (for general awareness)."""
        detected = [
            DetectedSoftware(name=e.name, version=e.version, source="database")
            for e in EOL_DATABASE
        ]
        return self.check(detected)

    def _check_one(self, sw: DetectedSoftware) -> EOLWarning | None:
        """Check one detected software against the database."""
        # Try exact match first
        lifecycle = self._db.get((sw.name, sw.version))

        # Try major version match (e.g., "3.12.3" → "3.12")
        if not lifecycle and "." in sw.version:
            major = sw.version.rsplit(".", 1)[0]
            lifecycle = self._db.get((sw.name, major))
        if not lifecycle:
            # Try just major version number
            major = sw.version.split(".")[0]
            lifecycle = self._db.get((sw.name, major))

        if not lifecycle:
            return None  # Unknown software/version

        if lifecycle.eol_date == "active":
            return EOLWarning(
                software=sw.name,
                version=sw.version,
                eol_date="active",
                days_until_eol=999,
                status="ok",
                severity="info",
                recommendation=f"{sw.name} {sw.version} is actively supported.",
                risk_score=0.0,
                source=sw.source,
            )

        eol = date.fromisoformat(lifecycle.eol_date)
        days_until = (eol - self.today).days

        if days_until < 0:
            # Already EOL
            months_past = abs(days_until) // 30
            return EOLWarning(
                software=sw.name,
                version=sw.version,
                eol_date=lifecycle.eol_date,
                days_until_eol=days_until,
                status="eol",
                severity="critical",
                recommendation=(
                    f"{sw.name} {sw.version} reached EOL on {lifecycle.eol_date} "
                    f"({months_past} months ago). Upgrade immediately. "
                    f"No security patches are being released."
                ),
                risk_score=min(10.0, 7.0 + months_past * 0.3),
                source=sw.source,
            )
        elif days_until < 180:
            # Approaching EOL (within 6 months)
            return EOLWarning(
                software=sw.name,
                version=sw.version,
                eol_date=lifecycle.eol_date,
                days_until_eol=days_until,
                status="approaching",
                severity="warning",
                recommendation=(
                    f"{sw.name} {sw.version} reaches EOL on {lifecycle.eol_date} "
                    f"({days_until} days). Plan upgrade now."
                ),
                risk_score=max(3.0, 6.0 - days_until * 0.02),
                source=sw.source,
            )
        else:
            return EOLWarning(
                software=sw.name,
                version=sw.version,
                eol_date=lifecycle.eol_date,
                days_until_eol=days_until,
                status="ok",
                severity="info",
                recommendation=(
                    f"{sw.name} {sw.version} supported until {lifecycle.eol_date} "
                    f"({days_until} days remaining)."
                ),
                risk_score=0.0,
                source=sw.source,
            )
