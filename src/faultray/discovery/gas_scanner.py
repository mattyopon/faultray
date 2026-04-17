# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""FaultRay GAS (Google Apps Script) Scanner.

Discovers all GAS scripts in a Google Workspace organization,
analyzes ownership, dependencies, and personalization risks.

Requires OAuth2 credentials with these scopes:
- drive.readonly (discover .gs files)
- script.projects.readonly (triggers, deployments)
- admin.directory.user.readonly (owner status check)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional Google API imports – gracefully handled
# ---------------------------------------------------------------------------

try:
    from google.oauth2 import service_account  # type: ignore[import-untyped]
    from googleapiclient.discovery import build  # type: ignore[import-untyped]

    _GOOGLE_AVAILABLE = True
except ImportError:  # pragma: no cover
    _GOOGLE_AVAILABLE = False


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class GASScript:
    """Represents a single Google Apps Script project."""

    id: str
    name: str
    owner_email: str
    owner_name: str
    created_at: datetime
    updated_at: datetime
    last_executed: datetime | None
    shared_with: list[str] = field(default_factory=list)
    triggers: list[dict[str, Any]] = field(default_factory=list)
    linked_services: list[str] = field(default_factory=list)
    drive_location: str = ""
    status: str = "active"  # "active" | "dormant" | "orphaned"
    owner_status: str = "active"  # "active" | "departed" | "unknown"


@dataclass
class GASRisk:
    """Risk assessment for a single GAS script."""

    script_id: str
    risk_score: float  # 0-10
    risk_level: str  # "critical" | "warning" | "ok"
    reasons: list[str] = field(default_factory=list)
    owner_status: str = "active"
    dependent_users: int = 0
    has_backup_owner: bool = False


@dataclass
class GASScanResult:
    """Full organization GAS scan result."""

    organization: str
    total_scripts: int
    critical_count: int
    warning_count: int
    ok_count: int
    scripts: list[GASScript] = field(default_factory=list)
    risks: list[GASRisk] = field(default_factory=list)
    scan_timestamp: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""

        def _fmt(dt: datetime | None) -> str | None:
            return dt.isoformat() if dt else None

        return {
            "organization": self.organization,
            "total_scripts": self.total_scripts,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "ok_count": self.ok_count,
            "scan_timestamp": _fmt(self.scan_timestamp),
            "scripts": [
                {
                    "id": s.id,
                    "name": s.name,
                    "owner_email": s.owner_email,
                    "owner_name": s.owner_name,
                    "created_at": _fmt(s.created_at),
                    "updated_at": _fmt(s.updated_at),
                    "last_executed": _fmt(s.last_executed),
                    "shared_with": s.shared_with,
                    "triggers": s.triggers,
                    "linked_services": s.linked_services,
                    "drive_location": s.drive_location,
                    "status": s.status,
                    "owner_status": s.owner_status,
                }
                for s in self.scripts
            ],
            "risks": [
                {
                    "script_id": r.script_id,
                    "risk_score": r.risk_score,
                    "risk_level": r.risk_level,
                    "reasons": r.reasons,
                    "owner_status": r.owner_status,
                    "dependent_users": r.dependent_users,
                    "has_backup_owner": r.has_backup_owner,
                }
                for r in self.risks
            ],
        }


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class GASScanner:
    """Scan a Google Workspace organization for GAS scripts and their risks."""

    def __init__(
        self,
        credentials_path: str | None = None,
        domain: str | None = None,
    ) -> None:
        """Initialize with Google OAuth2 credentials.

        Args:
            credentials_path: Path to service account JSON credentials file.
            domain: Google Workspace domain (e.g. "example.co.jp").
        """
        self.credentials_path = credentials_path
        self.domain = domain
        self._drive_service: Any = None
        self._script_service: Any = None
        self._admin_service: Any = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self) -> GASScanResult:
        """Full organization scan using Google APIs.

        Raises:
            ImportError: If google-api-python-client is not installed.
            RuntimeError: If credentials_path is not provided.
        """
        if not _GOOGLE_AVAILABLE:
            raise ImportError(
                "google-api-python-client and google-auth are required for live scans. "
                "Install them with: pip install google-api-python-client google-auth"
            )
        if not self.credentials_path:
            raise RuntimeError(
                "credentials_path is required for live scans. "
                "Use scan_demo() for a demo without credentials."
            )

        self._init_services()
        scripts = self._discover_scripts()
        for script in scripts:
            script.triggers = self._analyze_triggers(script.id)
            script.owner_status = self._check_owner_status(script.owner_email)
            script.linked_services = self._infer_dependencies(script)

        risks = [self._calculate_risk(s) for s in scripts]
        critical = sum(1 for r in risks if r.risk_level == "critical")
        warning = sum(1 for r in risks if r.risk_level == "warning")
        ok = sum(1 for r in risks if r.risk_level == "ok")

        return GASScanResult(
            organization=self.domain or "Unknown Org",
            total_scripts=len(scripts),
            critical_count=critical,
            warning_count=warning,
            ok_count=ok,
            scripts=scripts,
            risks=risks,
        )

    def scan_demo(self, org_name: str = "Example Corp") -> GASScanResult:
        """Generate realistic demo data without API calls.

        Args:
            org_name: Organization name for the report.

        Returns:
            A GASScanResult populated with realistic Japanese business context demo data.
        """
        scripts = self._generate_demo_scripts()
        for script in scripts:
            script.linked_services = self._infer_dependencies(script)

        risks = [self._calculate_risk(s) for s in scripts]
        critical = sum(1 for r in risks if r.risk_level == "critical")
        warning = sum(1 for r in risks if r.risk_level == "warning")
        ok = sum(1 for r in risks if r.risk_level == "ok")

        return GASScanResult(
            organization=org_name,
            total_scripts=len(scripts),
            critical_count=critical,
            warning_count=warning,
            ok_count=ok,
            scripts=scripts,
            risks=risks,
        )

    # ------------------------------------------------------------------
    # Google API helpers (used by scan())
    # ------------------------------------------------------------------

    def _init_services(self) -> None:
        """Initialize Google API service clients."""
        scopes = [
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/script.projects.readonly",
            "https://www.googleapis.com/auth/admin.directory.user.readonly",
        ]
        creds = service_account.Credentials.from_service_account_file(  # type: ignore[union-attr]
            self.credentials_path, scopes=scopes
        )
        self._drive_service = build("drive", "v3", credentials=creds)  # type: ignore[assignment]
        self._script_service = build("script", "v1", credentials=creds)  # type: ignore[assignment]
        self._admin_service = build("admin", "directory_v1", credentials=creds)  # type: ignore[assignment]

    def _discover_scripts(self) -> list[GASScript]:
        """Google Drive API: find all GAS projects (.gs files) in the org."""
        scripts: list[GASScript] = []
        page_token: str | None = None
        query = "mimeType='application/vnd.google-apps.script'"

        while True:
            params: dict[str, Any] = {
                "q": query,
                "fields": "nextPageToken, files(id, name, owners, createdTime, modifiedTime, parents)",
                "pageSize": 100,
                "supportsAllDrives": True,
                "includeItemsFromAllDrives": True,
            }
            if page_token:
                params["pageToken"] = page_token

            result = self._drive_service.files().list(**params).execute()
            for f in result.get("files", []):
                owners = f.get("owners", [{}])
                owner = owners[0] if owners else {}
                now = datetime.now(tz=timezone.utc)
                script = GASScript(
                    id=f["id"],
                    name=f.get("name", "Unnamed"),
                    owner_email=owner.get("emailAddress", "unknown@example.com"),
                    owner_name=owner.get("displayName", "Unknown"),
                    created_at=datetime.fromisoformat(
                        f.get("createdTime", now.isoformat()).replace("Z", "+00:00")
                    ),
                    updated_at=datetime.fromisoformat(
                        f.get("modifiedTime", now.isoformat()).replace("Z", "+00:00")
                    ),
                    last_executed=None,
                    drive_location="/".join(f.get("parents", [])),
                )
                scripts.append(script)

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return scripts

    def _analyze_triggers(self, script_id: str) -> list[dict[str, Any]]:
        """Apps Script API: get triggers for a script."""
        try:
            result = (
                self._script_service.projects()
                .get(scriptId=script_id)
                .execute()
            )
            # Real API returns deployment/trigger info; simplified extraction
            triggers: list[dict[str, Any]] = []
            for deployment in result.get("deployments", []):
                entry_points = deployment.get("entryPoints", [])
                for ep in entry_points:
                    ep_type = ep.get("entryPointType", "")
                    triggers.append({"type": "time" if "TRIGGER" in ep_type else "manual", "raw": ep})
            return triggers
        except Exception:  # noqa: BLE001
            logger.debug("Could not fetch triggers for script %s", script_id)
            return []

    def _check_owner_status(self, email: str) -> str:
        """Admin SDK: check if owner is still an active user in the org."""
        try:
            result = self._admin_service.users().get(userKey=email).execute()
            suspended = result.get("suspended", False)
            archived = result.get("archived", False)
            if suspended or archived:
                return "departed"
            return "active"
        except Exception:  # noqa: BLE001
            return "unknown"

    # ------------------------------------------------------------------
    # Risk calculation (used by both scan() and scan_demo())
    # ------------------------------------------------------------------

    def _calculate_risk(self, script: GASScript) -> GASRisk:
        """Calculate personalization risk score for a script.

        Scoring rubric:
        - Owner departed: +4
        - Single owner / no shared access: +3
        - Not updated in 365+ days: +2
        - Has time-based triggers (critical automation): +1

        Risk level thresholds:
        - critical: score >= 7
        - warning:  score >= 4
        - ok:       score < 4
        """
        score = 0.0
        reasons: list[str] = []
        now = datetime.now(tz=timezone.utc)

        # Owner departed
        if script.owner_status == "departed":
            score += 4
            reasons.append("Owner has left the organization")

        # Single owner, no shared access
        if len(script.shared_with) <= 1:
            score += 3
            reasons.append("Only 1 person has access (personalization risk)")

        # No updates in 1+ year
        days_since_update = (now - script.updated_at).days
        if days_since_update > 365:
            score += 2
            reasons.append(f"Not updated in {days_since_update} days")

        # Has time-based triggers (business-critical automation)
        if any(t.get("type") == "time" for t in script.triggers):
            score += 1
            reasons.append("Has automated triggers (business-critical)")

        # Determine risk level
        if score >= 7:
            risk_level = "critical"
        elif score >= 4:
            risk_level = "warning"
        else:
            risk_level = "ok"

        # Estimate dependent users from shared_with list
        dependent_users = max(0, len(script.shared_with) - 1)
        has_backup_owner = len(script.shared_with) > 1

        return GASRisk(
            script_id=script.id,
            risk_score=score,
            risk_level=risk_level,
            reasons=reasons,
            owner_status=script.owner_status,
            dependent_users=dependent_users,
            has_backup_owner=has_backup_owner,
        )

    def _infer_dependencies(self, script: GASScript) -> list[str]:
        """Infer which Google Workspace services this script connects to.

        Uses script name heuristics to guess linked services.
        """
        services: list[str] = []
        name_lower = script.name.lower()

        keyword_map: list[tuple[str, str]] = [
            ("sheet", "Sheets"),
            ("スプレッド", "Sheets"),
            ("集計", "Sheets"),
            ("売上", "Sheets"),
            ("勤怠", "Sheets"),
            ("mail", "Gmail"),
            ("メール", "Gmail"),
            ("送信", "Gmail"),
            ("通知", "Gmail"),
            ("calendar", "Calendar"),
            ("カレンダー", "Calendar"),
            ("予定", "Calendar"),
            ("drive", "Drive"),
            ("ドライブ", "Drive"),
            ("form", "Forms"),
            ("フォーム", "Forms"),
            ("doc", "Docs"),
            ("ドキュメント", "Docs"),
            ("slide", "Slides"),
            ("スライド", "Slides"),
            ("chat", "Chat"),
            ("チャット", "Chat"),
            ("bigquery", "BigQuery"),
        ]

        for keyword, service in keyword_map:
            if keyword in name_lower and service not in services:
                services.append(service)

        # Default: most GAS scripts touch Sheets
        if not services:
            services.append("Sheets")

        return services

    # ------------------------------------------------------------------
    # Demo data generation
    # ------------------------------------------------------------------

    def _generate_demo_scripts(self) -> list[GASScript]:
        """Generate 17 realistic GAS scripts for a Japanese company."""
        now = datetime.now(tz=timezone.utc)

        def _dt(days_ago: int) -> datetime:
            return now - timedelta(days=days_ago)

        # --- CRITICAL (3 scripts): departed owner + single owner ---
        critical_scripts = [
            GASScript(
                id="gas_001",
                name="請求書自動送信.gs",
                owner_email="yamamoto.kenji@example.co.jp",
                owner_name="山本 健二",
                created_at=_dt(730),
                updated_at=_dt(400),
                last_executed=_dt(3),
                shared_with=["yamamoto.kenji@example.co.jp"],
                triggers=[{"type": "time", "schedule": "monthly"}],
                drive_location="経理部/請求書管理",
                status="active",
                owner_status="departed",
            ),
            GASScript(
                id="gas_002",
                name="採用通知自動化.gs",
                owner_email="tanaka.hiroshi@example.co.jp",
                owner_name="田中 浩",
                created_at=_dt(600),
                updated_at=_dt(500),
                last_executed=_dt(10),
                shared_with=["tanaka.hiroshi@example.co.jp"],
                triggers=[{"type": "time", "schedule": "weekly"}],
                drive_location="人事部/採用管理",
                status="active",
                owner_status="departed",
            ),
            GASScript(
                id="gas_003",
                name="取引先マスタ同期.gs",
                owner_email="suzuki.akira@example.co.jp",
                owner_name="鈴木 明",
                created_at=_dt(800),
                updated_at=_dt(450),
                last_executed=_dt(1),
                shared_with=["suzuki.akira@example.co.jp"],
                triggers=[{"type": "time", "schedule": "daily"}],
                drive_location="営業部/マスタ管理",
                status="active",
                owner_status="departed",
            ),
        ]

        # --- WARNING (5 scripts): not updated 1yr+ or single owner ---
        warning_scripts = [
            GASScript(
                id="gas_004",
                name="売上集計レポート.gs",
                owner_email="sato.yuki@example.co.jp",
                owner_name="佐藤 雪",
                created_at=_dt(900),
                updated_at=_dt(400),
                last_executed=_dt(5),
                shared_with=["sato.yuki@example.co.jp"],
                triggers=[{"type": "time", "schedule": "weekly"}],
                drive_location="営業部/レポート",
                status="active",
                owner_status="active",
            ),
            GASScript(
                id="gas_005",
                name="勤怠データ集計.gs",
                owner_email="ito.masao@example.co.jp",
                owner_name="伊藤 正雄",
                created_at=_dt(700),
                updated_at=_dt(380),
                last_executed=_dt(2),
                shared_with=["ito.masao@example.co.jp"],
                triggers=[{"type": "time", "schedule": "monthly"}],
                drive_location="人事部/勤怠管理",
                status="active",
                owner_status="active",
            ),
            GASScript(
                id="gas_006",
                name="営業日報自動送信.gs",
                owner_email="watanabe.jun@example.co.jp",
                owner_name="渡辺 純",
                created_at=_dt(550),
                updated_at=_dt(370),
                last_executed=_dt(1),
                shared_with=["watanabe.jun@example.co.jp"],
                triggers=[{"type": "time", "schedule": "daily"}],
                drive_location="営業部/日報",
                status="active",
                owner_status="active",
            ),
            GASScript(
                id="gas_007",
                name="在庫アラート通知.gs",
                owner_email="kobayashi.emi@example.co.jp",
                owner_name="小林 恵美",
                created_at=_dt(480),
                updated_at=_dt(390),
                last_executed=_dt(0),
                shared_with=["kobayashi.emi@example.co.jp"],
                triggers=[{"type": "time", "schedule": "daily"}],
                drive_location="製造部/在庫管理",
                status="active",
                owner_status="active",
            ),
            GASScript(
                id="gas_008",
                name="経費精算リマインダー.gs",
                owner_email="nakamura.taro@example.co.jp",
                owner_name="中村 太郎",
                created_at=_dt(600),
                updated_at=_dt(420),
                last_executed=_dt(7),
                shared_with=["nakamura.taro@example.co.jp"],
                triggers=[{"type": "time", "schedule": "monthly"}],
                drive_location="経理部/経費精算",
                status="active",
                owner_status="active",
            ),
        ]

        # --- OK (9 scripts): active owner, shared access, recently updated ---
        ok_scripts = [
            GASScript(
                id="gas_009",
                name="会議室予約カレンダー同期.gs",
                owner_email="yamada.hanako@example.co.jp",
                owner_name="山田 花子",
                created_at=_dt(200),
                updated_at=_dt(30),
                last_executed=_dt(0),
                shared_with=[
                    "yamada.hanako@example.co.jp",
                    "admin@example.co.jp",
                    "it-team@example.co.jp",
                ],
                triggers=[{"type": "time", "schedule": "hourly"}],
                drive_location="総務部/会議室管理",
                status="active",
                owner_status="active",
            ),
            GASScript(
                id="gas_010",
                name="顧客アンケート集計.gs",
                owner_email="fujita.keiko@example.co.jp",
                owner_name="藤田 恵子",
                created_at=_dt(300),
                updated_at=_dt(45),
                last_executed=_dt(3),
                shared_with=[
                    "fujita.keiko@example.co.jp",
                    "cs-team@example.co.jp",
                ],
                triggers=[{"type": "form_submit"}],
                drive_location="カスタマーサービス/アンケート",
                status="active",
                owner_status="active",
            ),
            GASScript(
                id="gas_011",
                name="新入社員オンボーディング.gs",
                owner_email="matsumoto.ryo@example.co.jp",
                owner_name="松本 亮",
                created_at=_dt(150),
                updated_at=_dt(20),
                last_executed=_dt(14),
                shared_with=[
                    "matsumoto.ryo@example.co.jp",
                    "hr-team@example.co.jp",
                ],
                triggers=[{"type": "form_submit"}],
                drive_location="人事部/オンボーディング",
                status="active",
                owner_status="active",
            ),
            GASScript(
                id="gas_012",
                name="週次KPIダッシュボード更新.gs",
                owner_email="inoue.satoshi@example.co.jp",
                owner_name="井上 聡",
                created_at=_dt(250),
                updated_at=_dt(15),
                last_executed=_dt(2),
                shared_with=[
                    "inoue.satoshi@example.co.jp",
                    "management@example.co.jp",
                    "ops-team@example.co.jp",
                ],
                triggers=[{"type": "time", "schedule": "weekly"}],
                drive_location="経営企画部/KPI管理",
                status="active",
                owner_status="active",
            ),
            GASScript(
                id="gas_013",
                name="SNS投稿スケジューラー.gs",
                owner_email="kato.misaki@example.co.jp",
                owner_name="加藤 美咲",
                created_at=_dt(180),
                updated_at=_dt(10),
                last_executed=_dt(1),
                shared_with=[
                    "kato.misaki@example.co.jp",
                    "marketing@example.co.jp",
                ],
                triggers=[{"type": "time", "schedule": "daily"}],
                drive_location="マーケティング部/SNS管理",
                status="active",
                owner_status="active",
            ),
            GASScript(
                id="gas_014",
                name="サポートチケット自動振り分け.gs",
                owner_email="hayashi.daisuke@example.co.jp",
                owner_name="林 大輔",
                created_at=_dt(120),
                updated_at=_dt(8),
                last_executed=_dt(0),
                shared_with=[
                    "hayashi.daisuke@example.co.jp",
                    "support-team@example.co.jp",
                    "admin@example.co.jp",
                ],
                triggers=[{"type": "gmail_trigger"}],
                drive_location="サポート部/チケット管理",
                status="active",
                owner_status="active",
            ),
            GASScript(
                id="gas_015",
                name="請求書PDF生成.gs",
                owner_email="ogawa.noriko@example.co.jp",
                owner_name="小川 典子",
                created_at=_dt(360),
                updated_at=_dt(60),
                last_executed=_dt(5),
                shared_with=[
                    "ogawa.noriko@example.co.jp",
                    "accounting@example.co.jp",
                ],
                triggers=[{"type": "manual"}],
                drive_location="経理部/請求書",
                status="active",
                owner_status="active",
            ),
            GASScript(
                id="gas_016",
                name="商品マスタ更新通知.gs",
                owner_email="kimura.tomoko@example.co.jp",
                owner_name="木村 友子",
                created_at=_dt(90),
                updated_at=_dt(5),
                last_executed=_dt(0),
                shared_with=[
                    "kimura.tomoko@example.co.jp",
                    "product-team@example.co.jp",
                    "logistics@example.co.jp",
                ],
                triggers=[{"type": "sheet_edit"}],
                drive_location="商品管理部/マスタ",
                status="active",
                owner_status="active",
            ),
            GASScript(
                id="gas_017",
                name="月次収支レポート配信.gs",
                owner_email="nishimura.kazuya@example.co.jp",
                owner_name="西村 和也",
                created_at=_dt(400),
                updated_at=_dt(25),
                last_executed=_dt(10),
                shared_with=[
                    "nishimura.kazuya@example.co.jp",
                    "cfo@example.co.jp",
                    "accounting@example.co.jp",
                    "management@example.co.jp",
                ],
                triggers=[{"type": "time", "schedule": "monthly"}],
                drive_location="財務部/月次レポート",
                status="active",
                owner_status="active",
            ),
        ]

        return critical_scripts + warning_scripts + ok_scripts
