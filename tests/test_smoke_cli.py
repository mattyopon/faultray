# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI smoke tests — verify all commands respond to --help."""
import re
import subprocess
import pytest


def _get_all_commands():
    """Extract all command names from faultray --help.

    The Rich-rendered help uses box characters:
      │ command-name   description text  │
      │                continuation...   │
    Command lines have a non-space character immediately after '│ '.
    Continuation lines have spaces at that position.
    """
    result = subprocess.run(
        ["python3", "-m", "faultray", "--help"],
        capture_output=True, text=True, timeout=30
    )
    commands = []
    for line in result.stdout.splitlines():
        # Only process lines inside a Rich panel (start with the box char │)
        if not line.startswith("│ "):
            continue
        inner = line[2:]  # strip leading "│ "
        # Command lines: first character is non-space (name starts immediately)
        # Description-continuation lines: first character is space
        if not inner or inner[0] == " ":
            continue
        parts = inner.split()
        if not parts:
            continue
        cmd = parts[0]
        # Skip option lines (e.g. --help, --version)
        if cmd.startswith("-"):
            continue
        # Accept only lowercase alphanumeric + hyphens + underscores (CLI command pattern)
        if re.match(r"^[a-z][a-z0-9_-]*$", cmd):
            commands.append(cmd)
    return commands


ALL_COMMANDS = _get_all_commands()


@pytest.mark.skipif(not ALL_COMMANDS, reason="No commands found in faultray --help")
@pytest.mark.parametrize("command", ALL_COMMANDS)
def test_command_help(command):
    """Every CLI command should respond to --help without error."""
    result = subprocess.run(
        ["python3", "-m", "faultray", command, "--help"],
        capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, (
        f"{command} --help failed:\nstdout: {result.stdout[:500]}\nstderr: {result.stderr[:500]}"
    )
