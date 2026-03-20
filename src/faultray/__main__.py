# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Entry point for ``python -m faultray`` — delegates to the CLI.

Running ``python -m faultray.mcp_server`` is handled directly by
``faultray/mcp_server.py``'s ``if __name__ == '__main__'`` block and the
``main()`` function registered there.

This file makes the *package* itself runnable:
    python -m faultray          → opens the Typer CLI (same as ``faultray`` command)
    python -m faultray.mcp_server → starts the MCP server over stdio
"""

from __future__ import annotations

from faultray.cli import app

if __name__ == "__main__":
    app()
