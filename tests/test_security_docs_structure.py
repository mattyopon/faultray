"""Regression: SECURITY.md + runbook doc structure (#96, #98).

Guards:
- SECURITY.md has a "Secrets Rotation Policy" section (#96)
- docs/incident-response-runbook.md exists with the required sections (#98)
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def test_security_md_documents_rotation_sla():
    text = (_ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "Secrets Rotation Policy" in text, (
        "SECURITY.md must contain a 'Secrets Rotation Policy' section (#96)"
    )
    # Key terms that anchor the policy
    for needle in ("24 hours", "Stripe", "Supabase"):
        assert needle in text, (
            f"SECURITY.md rotation section missing '{needle}' — restore or "
            f"update the table to cover this credential"
        )


def test_incident_runbook_exists_and_covers_core_scenarios():
    runbook = _ROOT / "docs" / "incident-response-runbook.md"
    assert runbook.exists(), "docs/incident-response-runbook.md missing (#98)"

    text = runbook.read_text(encoding="utf-8")
    for section in (
        "Severity classification",
        "SEV-1",
        "72-hour",          # GDPR breach notification window
        "Stakeholder escalation",
        "Post-incident review",
    ):
        assert section in text, (
            f"incident-response-runbook.md missing section '{section}' (#98)"
        )


def test_security_md_links_runbook():
    text = (_ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "incident-response-runbook.md" in text, (
        "SECURITY.md must link to docs/incident-response-runbook.md (#98)"
    )
