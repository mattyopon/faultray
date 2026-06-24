"""Tests for coupon code management (faultray.coupon)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from faultray.coupon import (
    Coupon,
    RedeemedCoupon,
    _CODE_PREFIX,
    _VALID_TIERS,
    create_coupon,
    generate_code,
    get_active_coupon_tier,
    list_coupons,
    redeem_coupon,
    revoke_coupon,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_faultray_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect ~/.faultray to a temporary directory for all coupon tests."""
    import faultray.coupon as coupon_mod

    fake_dir = tmp_path / ".faultray"
    fake_dir.mkdir()

    monkeypatch.setattr(coupon_mod, "_FAULTRAY_DIR", fake_dir)
    monkeypatch.setattr(coupon_mod, "_COUPONS_FILE", fake_dir / "coupons.json")
    monkeypatch.setattr(coupon_mod, "_LICENSE_FILE", fake_dir / "license.json")


# ---------------------------------------------------------------------------
# generate_code
# ---------------------------------------------------------------------------


class TestGenerateCode:
    def test_format(self) -> None:
        code = generate_code()
        assert code.startswith(f"{_CODE_PREFIX}-")
        parts = code.split("-")
        assert len(parts) == 4
        assert parts[0] == _CODE_PREFIX
        for seg in parts[1:]:
            assert len(seg) == 4
            assert seg.isalnum()
            assert seg == seg.upper()

    def test_uniqueness(self) -> None:
        codes = {generate_code() for _ in range(200)}
        # With 36^12 combinations, collision probability in 200 draws is negligible
        assert len(codes) == 200


# ---------------------------------------------------------------------------
# Coupon.is_valid / days_remaining
# ---------------------------------------------------------------------------


class TestCouponValidity:
    def _make(self, **kwargs: object) -> Coupon:
        now = datetime.now(tz=timezone.utc)
        defaults: dict = {
            "code": "FRAY-TEST-0001-AAAA",
            "tier": "business",
            "days": 30,
            "max_uses": 0,
            "current_uses": 0,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=30)).isoformat(),
            "note": "",
            "revoked": False,
        }
        defaults.update(kwargs)
        return Coupon(**defaults)  # type: ignore[arg-type]

    def test_valid_coupon(self) -> None:
        c = self._make()
        assert c.is_valid() is True

    def test_revoked_coupon(self) -> None:
        c = self._make(revoked=True)
        assert c.is_valid() is False

    def test_expired_coupon(self) -> None:
        past = datetime.now(tz=timezone.utc) - timedelta(days=1)
        c = self._make(expires_at=past.isoformat())
        assert c.is_valid() is False

    def test_max_uses_reached(self) -> None:
        c = self._make(max_uses=3, current_uses=3)
        assert c.is_valid() is False

    def test_max_uses_not_yet_reached(self) -> None:
        c = self._make(max_uses=3, current_uses=2)
        assert c.is_valid() is True

    def test_unlimited_uses(self) -> None:
        c = self._make(max_uses=0, current_uses=9999)
        assert c.is_valid() is True

    def test_days_remaining(self) -> None:
        now = datetime.now(tz=timezone.utc)
        c = self._make(expires_at=(now + timedelta(days=7, hours=1)).isoformat())
        assert c.days_remaining() == 7

    def test_days_remaining_expired(self) -> None:
        past = datetime.now(tz=timezone.utc) - timedelta(days=1)
        c = self._make(expires_at=past.isoformat())
        assert c.days_remaining() == 0


# ---------------------------------------------------------------------------
# create_coupon
# ---------------------------------------------------------------------------


class TestCreateCoupon:
    def test_creates_coupon(self) -> None:
        coupon = create_coupon(tier="business", days=30)
        assert coupon.tier == "business"
        assert coupon.days == 30
        assert coupon.code.startswith("FRAY-")
        assert coupon.revoked is False
        assert coupon.current_uses == 0

    def test_normalises_tier_case(self) -> None:
        coupon = create_coupon(tier="BUSINESS", days=14)
        assert coupon.tier == "business"

    def test_invalid_tier_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid tier"):
            create_coupon(tier="free", days=30)

    def test_persists_to_file(self, tmp_path: Path) -> None:
        import faultray.coupon as m

        create_coupon(tier="pro", days=7)
        data = json.loads(m._COUPONS_FILE.read_text())
        assert len(data) == 1
        assert data[0]["tier"] == "pro"

    def test_multiple_coupons_unique_codes(self) -> None:
        codes = {create_coupon(tier="pro", days=7).code for _ in range(10)}
        assert len(codes) == 10

    def test_note_stored(self) -> None:
        coupon = create_coupon(tier="enterprise", days=1, note="VIP demo")
        assert coupon.note == "VIP demo"

    def test_max_uses_stored(self) -> None:
        coupon = create_coupon(tier="pro", days=30, max_uses=5)
        assert coupon.max_uses == 5

    def test_all_valid_tiers(self) -> None:
        for tier in _VALID_TIERS:
            c = create_coupon(tier=tier, days=1)
            assert c.tier == tier


# ---------------------------------------------------------------------------
# redeem_coupon
# ---------------------------------------------------------------------------


class TestRedeemCoupon:
    def test_basic_redeem(self) -> None:
        coupon = create_coupon(tier="business", days=30)
        redeemed = redeem_coupon(coupon.code)
        assert redeemed.tier == "business"
        assert redeemed.code == coupon.code

    def test_increments_use_count(self) -> None:
        coupon = create_coupon(tier="pro", days=7, max_uses=3)
        redeem_coupon(coupon.code)
        coupons = list_coupons()
        assert coupons[0].current_uses == 1

    def test_writes_license_json(self) -> None:
        import faultray.coupon as m

        coupon = create_coupon(tier="business", days=30)
        redeem_coupon(coupon.code)
        data = json.loads(m._LICENSE_FILE.read_text())
        assert "coupon" in data
        assert data["coupon"]["tier"] == "business"

    def test_code_normalised(self) -> None:
        coupon = create_coupon(tier="pro", days=7)
        redeemed = redeem_coupon(coupon.code.lower())
        assert redeemed.code == coupon.code

    def test_unknown_code_raises(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            redeem_coupon("FRAY-ZZZZ-ZZZZ-ZZZZ")

    def test_revoked_coupon_raises(self) -> None:
        coupon = create_coupon(tier="pro", days=7)
        revoke_coupon(coupon.code)
        with pytest.raises(ValueError, match="revoked"):
            redeem_coupon(coupon.code)

    def test_exhausted_coupon_raises(self) -> None:
        coupon = create_coupon(tier="pro", days=7, max_uses=1)
        redeem_coupon(coupon.code)
        with pytest.raises(ValueError, match="expired or has reached"):
            redeem_coupon(coupon.code)

    def test_expired_coupon_raises(self) -> None:
        import faultray.coupon as m

        coupon = create_coupon(tier="pro", days=1)
        # Forcibly set expiry in the past
        coupons = m._load_coupons()
        past = (datetime.now(tz=timezone.utc) - timedelta(days=2)).isoformat()
        coupons[0].expires_at = past
        m._save_coupons(coupons)

        with pytest.raises(ValueError, match="expired or has reached"):
            redeem_coupon(coupon.code)

    def test_active_until_is_days_from_now(self) -> None:
        coupon = create_coupon(tier="business", days=30)
        now = datetime.now(tz=timezone.utc)
        redeemed = redeem_coupon(coupon.code)
        active_until = datetime.fromisoformat(redeemed.active_until)
        if active_until.tzinfo is None:
            active_until = active_until.replace(tzinfo=timezone.utc)
        diff = active_until - now
        assert 29 <= diff.days <= 30  # allow 1-day slack for test speed


# ---------------------------------------------------------------------------
# revoke_coupon
# ---------------------------------------------------------------------------


class TestRevokeCoupon:
    def test_revoke(self) -> None:
        coupon = create_coupon(tier="pro", days=7)
        revoked = revoke_coupon(coupon.code)
        assert revoked.revoked is True

    def test_persists_revocation(self) -> None:
        coupon = create_coupon(tier="pro", days=7)
        revoke_coupon(coupon.code)
        coupons = list_coupons()
        assert coupons[0].revoked is True

    def test_unknown_code_raises(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            revoke_coupon("FRAY-ZZZZ-ZZZZ-ZZZZ")


# ---------------------------------------------------------------------------
# list_coupons
# ---------------------------------------------------------------------------


class TestListCoupons:
    def test_empty_when_no_file(self) -> None:
        assert list_coupons() == []

    def test_returns_all(self) -> None:
        create_coupon(tier="pro", days=7)
        create_coupon(tier="business", days=30)
        coupons = list_coupons()
        assert len(coupons) == 2


# ---------------------------------------------------------------------------
# get_active_coupon_tier
# ---------------------------------------------------------------------------


class TestGetActiveCouponTier:
    def test_no_license_returns_none(self) -> None:
        assert get_active_coupon_tier() is None

    def test_active_coupon_returns_tier(self) -> None:
        coupon = create_coupon(tier="business", days=30)
        redeem_coupon(coupon.code)
        assert get_active_coupon_tier() == "business"

    def test_expired_redeemed_returns_none(self) -> None:
        import faultray.coupon as m

        coupon = create_coupon(tier="business", days=1)
        redeem_coupon(coupon.code)

        # Forcibly expire the license
        data = json.loads(m._LICENSE_FILE.read_text())
        past = (datetime.now(tz=timezone.utc) - timedelta(days=2)).isoformat()
        data["coupon"]["active_until"] = past
        m._LICENSE_FILE.write_text(json.dumps(data))

        assert get_active_coupon_tier() is None


# ---------------------------------------------------------------------------
# Integration: licensing.get_active_tier picks up coupon tier
# ---------------------------------------------------------------------------


class TestLicensingIntegration:
    def test_coupon_tier_reflected_in_get_active_tier(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """After redeeming a business coupon, get_active_tier() returns BUSINESS."""
        from faultray.api.billing import PricingTier
        from faultray.licensing import get_active_tier

        # Ensure no license key is set
        monkeypatch.delenv("FAULTRAY_LICENSE_KEY", raising=False)
        monkeypatch.delenv("FAULTRAY_LICENSE_SECRET", raising=False)

        coupon = create_coupon(tier="business", days=30)
        redeem_coupon(coupon.code)

        assert get_active_tier() == PricingTier.BUSINESS

    def test_no_coupon_returns_free(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from faultray.api.billing import PricingTier
        from faultray.licensing import get_active_tier

        monkeypatch.delenv("FAULTRAY_LICENSE_KEY", raising=False)
        monkeypatch.delenv("FAULTRAY_LICENSE_SECRET", raising=False)

        assert get_active_tier() == PricingTier.FREE


# ---------------------------------------------------------------------------
# license.json HMAC signing (forgery resistance)
# ---------------------------------------------------------------------------


class TestCouponLicenseSigning:
    """When FAULTRAY_LICENSE_SECRET is set, license.json must be signed and
    tamper/forgery is rejected (fail closed)."""

    def test_redeem_writes_signature_when_secret_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import faultray.coupon as m

        monkeypatch.setenv("FAULTRAY_LICENSE_SECRET", "topsecret")
        coupon = create_coupon(tier="business", days=30)
        redeem_coupon(coupon.code)
        data = json.loads(m._LICENSE_FILE.read_text())
        assert "coupon_sig" in data and len(data["coupon_sig"]) == 64
        assert get_active_coupon_tier() == "business"

    def test_forged_tier_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import faultray.coupon as m

        monkeypatch.setenv("FAULTRAY_LICENSE_SECRET", "topsecret")
        coupon = create_coupon(tier="pro", days=30)
        redeem_coupon(coupon.code)

        # Attacker edits the tier to enterprise WITHOUT the secret (cannot re-sign).
        data = json.loads(m._LICENSE_FILE.read_text())
        data["coupon"]["tier"] = "enterprise"
        m._LICENSE_FILE.write_text(json.dumps(data))

        # Forgery fails the HMAC check and is ignored.
        assert get_active_coupon_tier() is None

    def test_unsigned_file_rejected_when_secret_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import faultray.coupon as m

        # Write an unsigned (legacy/hand-crafted) license while a secret is set.
        monkeypatch.setenv("FAULTRAY_LICENSE_SECRET", "topsecret")
        future = (datetime.now(tz=timezone.utc) + timedelta(days=10)).isoformat()
        m._FAULTRAY_DIR.mkdir(parents=True, exist_ok=True)
        m._LICENSE_FILE.write_text(json.dumps({"coupon": {
            "code": "FRAY-AAAA-BBBB-CCCC", "tier": "enterprise",
            "redeemed_at": future, "active_until": future,
        }}))
        assert get_active_coupon_tier() is None

    def test_secret_rotation_invalidates_old_signature(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FAULTRAY_LICENSE_SECRET", "old-secret")
        coupon = create_coupon(tier="business", days=30)
        redeem_coupon(coupon.code)
        assert get_active_coupon_tier() == "business"
        # Rotate the secret: the old signature no longer verifies.
        monkeypatch.setenv("FAULTRAY_LICENSE_SECRET", "new-secret")
        assert get_active_coupon_tier() is None

    def test_unsigned_flow_still_works_without_secret(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Local convenience path: no secret => unsigned redeem/read still works.
        monkeypatch.delenv("FAULTRAY_LICENSE_SECRET", raising=False)
        coupon = create_coupon(tier="pro", days=30)
        redeem_coupon(coupon.code)
        assert get_active_coupon_tier() == "pro"
