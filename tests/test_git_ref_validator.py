"""Regression: git ref validator blocks argument-injection inputs (#102).

Conservative posture: only reject inputs that git would re-interpret as
CLI options or shell metacharacters. Normal git ref syntax (HEAD~1,
branch^2, refs/tags/v1.0-rc1, `<ref>:<path>`, reflog @{N}) must pass.
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
        "HEAD",
        "HEAD~1",
        "HEAD~3",
        "branch^1",
        "branch^2",
        "refs/tags/v1.0-rc1",
        "refs/tags/v1.0-beta",
        "a:b",                # `<ref>:<path>` syntax used by `git show`
        "feature-branch@{0}", # reflog syntax
        "feat/foo..main",     # range expressions in ref position
    ],
)
def test_accepts_legit_git_refs(value: str) -> None:
    _assert_safe_git_ref(value)


@pytest.mark.parametrize(
    "bad",
    [
        "",                                      # empty
        "a" * 257,                               # too long
        "--upload-pack=rm -rf /",                # option injection attempt
        "-o/tmp/out",                            # short option form
        "--output=/tmp/x",                       # long option form
        "ref with space",                        # whitespace reserved
        "ref\ncommand",                          # newline
        "ref\ttab",                              # tab
        "ref\x00null",                           # NUL
        "ref\\backslash",                        # backslash
        "ref`cmd`",                              # backtick
    ],
)
def test_rejects_unsafe_refs(bad: str) -> None:
    with pytest.raises(ValueError):
        _assert_safe_git_ref(bad)


def test_error_message_includes_field_name() -> None:
    with pytest.raises(ValueError, match=r"base_ref"):
        _assert_safe_git_ref("--hack", name="base_ref")
