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

try:
    import msvcrt as _msvcrt  # Windows-only stdlib

    _MSVCRT_AVAILABLE = True
except ImportError:  # POSIX
    _MSVCRT_AVAILABLE = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# File-based locking
# ---------------------------------------------------------------------------

_LOCK_FILE = Path.home() / ".faultray" / ".coupon.lock"


@contextmanager
def _coupon_lock() -> Generator[None, None, None]:
    """Exclusive file lock for atomic coupon read-modify-write operations.

    On POSIX systems this uses ``fcntl.flock``; on Windows it uses
    ``msvcrt.locking``. Both provide mutual exclusion for concurrent
    redeem/create/revoke operations so usage counters are not lost. Only when
    neither primitive is available is the lock skipped (with a warning).
    """
    _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

    if _FCNTL_AVAILABLE:
        with open(_LOCK_FILE, "w") as _lf:
            _fcntl.flock(_lf, _fcntl.LOCK_EX)
            try:
                yield
            finally:
                _fcntl.flock(_lf, _fcntl.LOCK_UN)
        return

    if _MSVCRT_AVAILABLE:
        with open(_LOCK_FILE, "w") as _lf:
            # Lock a single byte; msvcrt.locking blocks until the region is free.
            _lf.write("0")
            _lf.flush()
            _lf.seek(0)
            _msvcrt.locking(_lf.fileno(), _msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                _lf.seek(0)
                _msvcrt.locking(_lf.fileno(), _msvcrt.LK_UNLCK, 1)
        return

    warnings.warn(
        "No file-locking primitive (fcntl/msvcrt) is available on this "
        "platform; coupon operations are not protected against concurrent "
        "access.",
        RuntimeWarning,
        stacklevel=3,
    )
    yield

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


def _restrict_permissions(path: Path) -> None:
    """Make *path* readable/writable by the owner only (best effort)."""
    try:
        path.chmod(0o600)
    except OSError:  # e.g. filesystems without POSIX permissions
        logger.debug("Could not restrict permissions on %s", path)


def _load_coupons() -> list[Coupon]:
    """Load all coupons from ~/.faultray/coupons.json.

    A single malformed *record* is skipped (logged) so one bad entry does not
    discard the whole registry. A corrupt *file* (invalid JSON or wrong
    top-level type) raises :class:`ValueError` rather than silently returning an
    empty list: mutating callers (create/redeem/revoke) must not overwrite a
    corrupt store with an empty one and permanently lose valid coupons.
    """
    if not _COUPONS_FILE.exists():
        return []
    try:
        raw = json.loads(_COUPONS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("coupons.json is unreadable or corrupt: %s", exc)
        raise ValueError(
            "coupons.json is corrupt or unreadable; refusing to proceed to "
            "avoid overwriting it. Inspect or remove the file manually."
        ) from exc
    if not isinstance(raw, list):
        raise ValueError("coupons.json has an unexpected format (expected a list).")

    coupons: list[Coupon] = []
    for item in raw:
        try:
            coupons.append(Coupon.from_dict(item))
        except (KeyError, TypeError) as exc:
            logger.warning("Skipping malformed coupon record: %s", exc)
    return coupons


def _save_coupons(coupons: list[Coupon]) -> None:
    """Persist coupon list to ~/.faultray/coupons.json (owner-only readable)."""
    _ensure_dir()
    data = [c.to_dict() for c in coupons]
    _COUPONS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _restrict_permissions(_COUPONS_FILE)


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
    _restrict_permissions(_LICENSE_FILE)


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
    if max_uses < 0:
        # A negative value would otherwise behave like unlimited (is_valid only
        # enforces the limit when max_uses > 0).
        raise ValueError("max_uses must be 0 (unlimited) or a positive integer")

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
            # Cap the granted access at the coupon's own expiry so redeeming on
            # the last valid day cannot extend access to ~2x the intended window.
            expires = datetime.fromisoformat(coupon.expires_at)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < active_until:
                active_until = expires

            redeemed = RedeemedCoupon(
                code=code,
                tier=coupon.tier,
                redeemed_at=now.isoformat(),
                active_until=active_until.isoformat(),
            )
            # Write the license FIRST; only then consume a use. If the license
            # write fails we must not have consumed a coupon use (which would
            # corrupt usage accounting without granting access).
            _save_license(redeemed)
            coupons[i].current_uses += 1
            _save_coupons(coupons)
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
    # TODO(review/U4): ~/.faultray/license.json is plain, unsigned JSON, so a
    # user with local filesystem write access can forge an enterprise tier by
    # editing it directly (local-CLI threat model). A real fix is to HMAC-sign
    # the redeemed-coupon record with FAULTRAY_LICENSE_SECRET and verify it
    # here, mirroring licensing.verify_license_key. Deferred: requires a signing
    # secret to be provisioned to the redemption path and breaks existing
    # unsigned license.json files. Server-side enforcement (billing.check_limit,
    # now fail-closed) is the authoritative gate.
    redeemed = _load_license()
    if redeemed is None:
        return None
    if redeemed.is_active():
        return redeemed.tier
    return None
