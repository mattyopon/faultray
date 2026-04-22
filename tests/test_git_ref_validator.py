"""Regression: git ref validator blocks argument-injection inputs (#102).

`code_risk_engine._assert_safe_git_ref` hardens three subprocess call
sites (git diff, git show, git log) against argument-injection when the
refs originate from untrusted input (future: web API; today: CLI).
"""

from __future__ import annotations

import pytest

from faultray.simulator.code_risk_engine import _assert_safe_git_ref


@pytest.mark.parametrize(
    "value",
    [
        "main",
        "develop",
        "v11.2.0",
        "feat/foo-bar",
        "release/v1.0",
        "a1b2c3d4",
        "HEAD~3",  # `~` is not allowed by our allow-list — see unsafe tests
    ][:-1],  # exclude HEAD~3 — ~ is reserved
)
def test_accepts_normal_refs(value: str) -> None:
    _assert_safe_git_ref(value)


@pytest.mark.parametrize(
    "bad",
    [
        "",                                      # empty
        "a" * 257,                               # too long
        "--upload-pack=rm -rf /",                # option injection attempt
        "-o/tmp/out",                            # short option form
        "--output=/tmp/x",                       # long option form
        "../etc/passwd",                         # relative path (rejected by '.' starter not in class)
        ".hidden",                               # starts with `.` (disallowed by leading class)
        "ref with space",
        "ref;cmd",                               # command separator (would be quoted by list form,
                                                 # but the strict regex rejects it defensively)
        "ref&&cmd",
        "ref|cmd",
        "ref\ncommand",
        "ref\x00null",
        "HEAD~1",                                # `~` reserved by our regex
        "feature^",                              # `^` reserved
        "a:b",                                   # `:` reserved
    ],
)
def test_rejects_unsafe_refs(bad: str) -> None:
    with pytest.raises(ValueError):
        _assert_safe_git_ref(bad)


def test_error_message_includes_field_name() -> None:
    with pytest.raises(ValueError, match=r"base_ref"):
        _assert_safe_git_ref("--hack", name="base_ref")
