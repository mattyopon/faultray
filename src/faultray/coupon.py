# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Coupon code management for FaultRay.

Coupon codes allow administrators to grant temporary tier access without
requiring a Stripe subscription.

Coupon code format: ``FRAY-XXXX-XXXX-XXXX``

Storage:
    ``~/.faultray/coupons.json``  — admin-side coupon registry
    ``~/.faultray/license.json``  — user-side redeemed coupon
"""

from __future__ import annotations

import json
import logging
import secrets
import string
import warnings
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator

try:
    import fcntl as _fcntl

    _FCNTL_AVAILABLE = True
except ImportError:  # Windows
    _FCNTL_AVAILABLE = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# File-based locking
# ---------------------------------------------------------------------------

_LOCK_FILE = Path.home() / ".faultray" / ".coupon.lock"


@contextmanager
def _coupon_lock() -> Generator[None, None, None]:
    """Exclusive file lock for atomic coupon read-modify-write operations.

    On POSIX systems this uses ``fcntl.flock`` for advisory locking.
    On Windows (where fcntl is unavailable) the lock is skipped and a
    warning is emitted, because concurrent access on Windows is unlikely in
    the current CLI-centric usage pattern.
    """
    if not _FCNTL_AVAILABLE:
        warnings.warn(
            "fcntl is not available on this platform; coupon operations are "
            "not protected against concurrent access.",
            RuntimeWarning,
            stacklevel=3,
        )
        yield
        return

    _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOCK_FILE, "w") as _lf:
        _fcntl.flock(_lf, _fcntl.LOCK_EX)
        try:
            yield
        finally:
            _fcntl.flock(_lf, _fcntl.LOCK_UN)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FAULTRAY_DIR = Path.home() / ".faultray"
_COUPONS_FILE = _FAULTRAY_DIR / "coupons.json"
_LICENSE_FILE = _FAULTRAY_DIR / "license.json"

_CODE_PREFIX = "FRAY"
_VALID_TIERS = ("pro", "business", "enterprise")

_ALPHABET = string.ascii_uppercase + string.digits


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Coupon:
    """A coupon code that grants temporary tier access."""

    code: str
    tier: str
    days: int
    max_uses: int  # 0 = unlimited
    current_uses: int
    created_at: str  # ISO-8601
    expires_at: str  # ISO-8601 (created_at + days)
    note: str
    revoked: bool = False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def is_valid(self, *, now: datetime | None = None) -> bool:
        """Return True if the coupon can still be redeemed."""
        if self.revoked:
            return False
        ts = now or datetime.now(tz=timezone.utc)
        expires = datetime.fromisoformat(self.expires_at)
        # Ensure timezone-aware comparison
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if ts > expires:
            return False
        if self.max_uses > 0 and self.current_uses >= self.max_uses:
            return False
        return True

    def days_remaining(self, *, now: datetime | None = None) -> int:
        """Return the number of days remaining until the coupon expires."""
        ts = now or datetime.now(tz=timezone.utc)
        expires = datetime.fromisoformat(self.expires_at)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        delta = expires - ts
        return max(0, delta.days)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Coupon:
        return cls(
            code=data["code"],
            tier=data["tier"],
            days=data["days"],
            max_uses=data["max_uses"],
            current_uses=data["current_uses"],
            created_at=data["created_at"],
            expires_at=data["expires_at"],
            note=data.get("note", ""),
            revoked=data.get("revoked", False),
        )


@dataclass
class RedeemedCoupon:
    """Redeemed coupon information stored in the user's license.json."""

    code: str
    tier: str
    redeemed_at: str  # ISO-8601
    active_until: str  # ISO-8601

    def is_active(self, *, now: datetime | None = None) -> bool:
        ts = now or datetime.now(tz=timezone.utc)
        until = datetime.fromisoformat(self.active_until)
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        return ts <= until

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> RedeemedCoupon:
        return cls(
            code=data["code"],
            tier=data["tier"],
            redeemed_at=data["redeemed_at"],
            active_until=data["active_until"],
        )


# ---------------------------------------------------------------------------
# Code generation
# ---------------------------------------------------------------------------


def generate_code() -> str:
    """Generate a unique coupon code in the format ``FRAY-XXXX-XXXX-XXXX``.

    Uses :func:`secrets.token_hex` as a source of randomness and selects
    characters from an uppercase alphanumeric alphabet.
    """
    raw = secrets.token_hex(12)  # 24 hex chars, more than enough
    chars: list[str] = []
    # Map each hex pair to an index in _ALPHABET (36 chars) via modulo
    for i in range(0, 24, 2):
        byte_val = int(raw[i : i + 2], 16)
        chars.append(_ALPHABET[byte_val % len(_ALPHABET)])
    segment1 = "".join(chars[0:4])
    segment2 = "".join(chars[4:8])
    segment3 = "".join(chars[8:12])
    return f"{_CODE_PREFIX}-{segment1}-{segment2}-{segment3}"


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def _ensure_dir() -> None:
    _FAULTRAY_DIR.mkdir(parents=True, exist_ok=True)


def _load_coupons() -> list[Coupon]:
    """Load all coupons from ~/.faultray/coupons.json."""
    if not _COUPONS_FILE.exists():
        return []
    try:
        raw = json.loads(_COUPONS_FILE.read_text(encoding="utf-8"))
        return [Coupon.from_dict(item) for item in raw]
    except Exception:
        logger.warning("Failed to load coupons.json; treating as empty", exc_info=True)
        return []


def _save_coupons(coupons: list[Coupon]) -> None:
    """Persist coupon list to ~/.faultray/coupons.json."""
    _ensure_dir()
    data = [c.to_dict() for c in coupons]
    _COUPONS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _load_license() -> RedeemedCoupon | None:
    """Load the redeemed coupon from ~/.faultray/license.json, if any."""
    if not _LICENSE_FILE.exists():
        return None
    try:
        raw = json.loads(_LICENSE_FILE.read_text(encoding="utf-8"))
        coupon_data = raw.get("coupon")
        if not coupon_data:
            return None
        return RedeemedCoupon.from_dict(coupon_data)
    except Exception:
        logger.warning("Failed to load license.json", exc_info=True)
        return None


def _save_license(redeemed: RedeemedCoupon) -> None:
    """Persist redeemed coupon to ~/.faultray/license.json."""
    _ensure_dir()
    # Preserve existing keys in license.json if present
    existing: dict = {}
    if _LICENSE_FILE.exists():
        try:
            existing = json.loads(_LICENSE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    existing["coupon"] = redeemed.to_dict()
    _LICENSE_FILE.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------


def create_coupon(
    *,
    tier: str,
    days: int,
    max_uses: int = 0,
    note: str = "",
) -> Coupon:
    """Create a new coupon and persist it to ``~/.faultray/coupons.json``.

    Parameters
    ----------
    tier:
        The pricing tier to grant (``"pro"``, ``"business"``, or
        ``"enterprise"``).
    days:
        Number of days the coupon remains valid after redemption.
    max_uses:
        Maximum number of times this coupon can be redeemed (0 = unlimited).
    note:
        Optional human-readable memo.

    Returns
    -------
    Coupon
        The newly created coupon.

    Raises
    ------
    ValueError
        If ``tier`` is not a valid paid tier.
    """
    tier = tier.lower()
    if tier not in _VALID_TIERS:
        raise ValueError(
            f"Invalid tier '{tier}'. Must be one of: {', '.join(_VALID_TIERS)}"
        )
    if days < 1:
        raise ValueError("days must be at least 1")

    now = datetime.now(tz=timezone.utc)
    expires = now + timedelta(days=days)

    with _coupon_lock():
        # Ensure uniqueness
        existing_codes = {c.code for c in _load_coupons()}
        code = generate_code()
        while code in existing_codes:
            code = generate_code()

        coupon = Coupon(
            code=code,
            tier=tier,
            days=days,
            max_uses=max_uses,
            current_uses=0,
            created_at=now.isoformat(),
            expires_at=expires.isoformat(),
            note=note,
            revoked=False,
        )

        coupons = _load_coupons()
        coupons.append(coupon)
        _save_coupons(coupons)
    return coupon


def redeem_coupon(code: str) -> RedeemedCoupon:
    """Redeem a coupon code and write the license to ``~/.faultray/license.json``.

    Parameters
    ----------
    code:
        The coupon code to redeem (e.g. ``FRAY-A1B2-C3D4-E5F6``).

    Returns
    -------
    RedeemedCoupon
        The redeemed coupon information.

    Raises
    ------
    ValueError
        If the code is not found, already revoked, expired, or exhausted.
    """
    code = code.strip().upper()
    with _coupon_lock():
        coupons = _load_coupons()
        for i, coupon in enumerate(coupons):
            if coupon.code != code:
                continue
            if coupon.revoked:
                raise ValueError(f"Coupon {code} has been revoked.")
            if not coupon.is_valid():
                raise ValueError(f"Coupon {code} is expired or has reached its usage limit.")

            now = datetime.now(tz=timezone.utc)
            active_until = now + timedelta(days=coupon.days)

            # Increment usage counter
            coupons[i].current_uses += 1
            _save_coupons(coupons)

            redeemed = RedeemedCoupon(
                code=code,
                tier=coupon.tier,
                redeemed_at=now.isoformat(),
                active_until=active_until.isoformat(),
            )
            _save_license(redeemed)
            return redeemed

        raise ValueError(f"Coupon code '{code}' not found.")


def revoke_coupon(code: str) -> Coupon:
    """Mark a coupon as revoked so it can no longer be redeemed.

    Returns
    -------
    Coupon
        The revoked coupon.

    Raises
    ------
    ValueError
        If the code is not found.
    """
    code = code.strip().upper()
    with _coupon_lock():
        coupons = _load_coupons()
        for i, coupon in enumerate(coupons):
            if coupon.code == code:
                coupons[i].revoked = True
                _save_coupons(coupons)
                return coupons[i]
        raise ValueError(f"Coupon code '{code}' not found.")


def list_coupons() -> list[Coupon]:
    """Return all coupons from ``~/.faultray/coupons.json``."""
    return _load_coupons()


def get_active_coupon_tier() -> str | None:
    """Return the tier string from an active redeemed coupon, or ``None``.

    This is the integration point for :func:`faultray.licensing.get_active_tier`.
    """
    redeemed = _load_license()
    if redeemed is None:
        return None
    if redeemed.is_active():
        return redeemed.tier
    return None
