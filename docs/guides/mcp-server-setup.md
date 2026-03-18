# FaultRay MCP Server Setup Guide

Connect FaultRay's infrastructure simulation engine to Claude Desktop, Claude Code, Cursor,
Windsurf, and any other MCP-compatible AI assistant.

---

## What is MCP?

Model Context Protocol (MCP) is an open standard that lets AI assistants call external tools,
read resources, and use templated prompts defined by third-party servers.  Once you add FaultRay
as an MCP server, Claude (or Cursor, etc.) can:

- Load your infrastructure YAML and immediately start asking questions about it
- Simulate failure scenarios ("what happens if the database goes down?")
- Find single points of failure
- Check Terraform plans for resilience regressions before `terraform apply`
- Run compliance checks against SOC 2, ISO 27001, PCI-DSS, or NIST CSF

No REST API, no web dashboard — the AI drives FaultRay directly through tools.

---

## Installation

### Option 1 — pip (recommended)

```bash
pip install faultray mcp
```

### Option 2 — pip with the mcp extra

```bash
pip install "faultray[mcp]"
```

### Option 3 — uvx (no permanent install, always latest)

```bash
# uvx downloads and runs in an isolated env each time
uvx --from "faultray[mcp]" python -m faultray.mcp_server
```

### Option 4 — pipx

```bash
pipx install "faultray[mcp]"
```

Verify the server starts without error:

```bash
python -m faultray.mcp_server
# Server should start and wait for stdio input — press Ctrl-C to exit
```

---

## Claude Desktop Setup

1. Find the Claude Desktop config file:
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

2. Copy the `mcp-server.json` from the FaultRay repository root into it
   (or merge the `mcpServers` block):

```json
{
  "mcpServers": {
    "faultray": {
      "command": "python",
      "args": ["-m", "faultray.mcp_server"],
      "env": {}
    }
  }
}
```

If you installed with `pipx`, use the `faultray-mcp` entry point instead:

```json
{
  "mcpServers": {
    "faultray": {
      "command": "faultray-mcp",
      "args": [],
      "env": {}
    }
  }
}
```

3. Restart Claude Desktop.
4. Click the **Tools** (hammer) icon — you should see `faultray` listed.

---

## Claude Code Setup

### Using the CLI

```bash
claude mcp add faultray -- python -m faultray.mcp_server
```

### Manual setup

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "faultray": {
      "command": "python",
      "args": ["-m", "faultray.mcp_server"],
      "env": {}
    }
  }
}
```

Verify:

```bash
claude mcp list
# Should show: faultray  python -m faultray.mcp_server
```

---

## Cursor Setup

1. Open **Cursor → Preferences → MCP**.
2. Click **Add MCP Server**.
3. Fill in:
   - **Name**: `faultray`
   - **Command**: `python`
   - **Args**: `-m faultray.mcp_server`
4. Click **Save** and restart Cursor.

---

## Windsurf / Other MCP Clients

Use the standard MCP server config. Any client that supports stdio transport will work:

```json
{
  "name": "faultray",
  "command": "python",
  "args": ["-m", "faultray.mcp_server"]
}
```

---

## Available Tools

Once connected, the following tools are available:

| Tool | Description |
|------|-------------|
| `load_infrastructure` | Load infrastructure YAML (paste as string) |
| `load_infrastructure_file` | Load infrastructure YAML from a file path |
| `simulate` | Simulate a component failure — shows cascade blast radius |
| `analyze_resilience` | Full resilience score (0-100) with breakdown and recommendations |
| `find_spof` | List all single points of failure |
| `what_if` | Preview score impact of adding replicas / enabling failover |
| `check_compliance` | Check against SOC 2, ISO 27001, PCI-DSS, or NIST CSF |
| `recommend_chaos` | Suggest chaos experiments ranked by priority |
| `predict_change_risk` | Predict risk level of a proposed infrastructure change |
| `generate_report` | Generate a resilience report (summary or detailed) |
| `tf_check` | Analyze a Terraform plan JSON for resilience regressions |
| `dora_assess` | Quick DORA compliance readiness check |

### Resources

| URI | Content |
|-----|---------|
| `faultray://version` | Current FaultRay version |
| `faultray://tools` | Full tool list with descriptions |
| `faultray://infrastructure` | Summary of the currently loaded infrastructure |

### Prompts

| Prompt | Purpose |
|--------|---------|
| `resilience_review` | Step-by-step guide for SRE infrastructure review |
| `terraform_review` | Step-by-step guide for Terraform plan safety review |

---

## Example Conversations

### "Load my infra.yaml and tell me about single points of failure"

```
User: Load /home/me/infra.yaml and find all single points of failure.

Claude: [calls load_infrastructure_file("/home/me/infra.yaml")]
Infrastructure loaded from 'infra.yaml'.
  Components : 6
  Dependencies : 7
  Resilience score : 62.0/100

[calls find_spof()]
Found 3 single points of failure:
1. postgresql (database) — 2 dependents (api-server-1, api-server-2)
2. nginx (load_balancer) — 2 dependents
3. redis (cache) — 1 dependent

The most critical SPOF is postgresql. With only 1 replica and no failover,
a database failure would take down both API servers simultaneously.
Run simulate("postgresql") to see the full blast radius.
```

### "Check my Terraform plan before I apply"

```
User: I have a plan at /tmp/plan.json — is it safe to apply?

Claude: [calls tf_check("/tmp/plan.json")]
Terraform Plan Resilience Analysis
  Score: 71.0 → 58.0 (-13.0)
  Recommendation: review recommended

The plan destroys aws_elasticache_replication_group.primary (risk level 8/10).
This introduces a new SPOF: your API servers will lose caching with no fallback.

Suggested mitigation: ensure your application handles cache misses gracefully
before applying, or provision a replacement cache in the same plan.
```

### "Check SOC 2 compliance"

```
User: Does my infrastructure pass SOC 2?

Claude: [calls check_compliance("soc2")]
SOC 2 Compliance: 50.0% (1/2 controls passing)

Passing:
  ✓ redundancy — All components have replicas >= 2

Failing:
  ✗ failover — 3 components lack failover enabled:
    postgresql, redis, rabbitmq

To fix: enable failover on these components, then re-run the check.
```

---

## Troubleshooting

### "Server not found" in Claude Desktop

- Verify `python -m faultray.mcp_server` runs without error in your terminal.
- Check that the `python` in your PATH matches the one where faultray is installed.
- Use an absolute path: `"command": "/usr/bin/python3"` or the virtualenv path.

### "mcp package not installed" error

```bash
pip install mcp
# or
pip install "faultray[mcp]"
```

### "No infrastructure loaded" when calling analysis tools

You must call `load_infrastructure` or `load_infrastructure_file` before using any analysis tool.
The server holds state only for the current session — reload after restarting.

### Tools don't appear in Claude

- Restart Claude Desktop / Claude Code after editing the config.
- Check the JSON config for syntax errors (trailing commas break JSON parsers).
- Run `claude mcp list` (Claude Code) to confirm the server is registered.

### Terraform plan analysis fails

The `tf_check` tool expects the output of `terraform show -json`, not the binary plan file:

```bash
terraform plan -out=plan.out
terraform show -json plan.out > plan.json   # this is what tf_check expects
```

---

## Next Steps

- **CI/CD gate**: Add FaultRay to your GitHub Actions pipeline — see [CI/CD Integration](../integrations/cicd.md).
- **Terraform safety net**: Full Terraform workflow guide — see [Terraform Safety Net](terraform-safety-net.md).
- **Python SDK**: Use FaultRay programmatically — see [Python SDK](../api/python-sdk.md).
