# APM Commands — CLI Reference

The `faultray apm` command group manages the FaultRay APM agent lifecycle and queries the
collector for metrics, agents, and alerts.

---

## faultray apm setup

Interactive APM setup wizard — the easiest way to get started with monitoring.

```
faultray apm setup
```

Walks you through:
1. Server configuration (collector URL, API key)
2. Collection interval selection with metric explanations
3. Agent configuration installation
4. Agent startup (background or foreground)
5. "What's next" panel with useful commands

**No flags.** The wizard prompts interactively for all options.

---

## faultray apm install

Install the FaultRay APM agent configuration.

```
faultray apm install [OPTIONS]
```

Creates `~/.faultray/agent.yaml` with the specified settings.

### Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--collector` | `-c` | `http://localhost:8080` | Collector server URL |
| `--api-key` | `-k` | `""` | API key for authentication |
| `--config-dir` | | `~/.faultray` | Directory for agent config |
| `--interval` | `-i` | `15` | Collection interval (seconds) |

### Examples

```bash
# Default install (localhost collector)
faultray apm install

# Remote collector
faultray apm install --collector http://faultray.internal:8080

# With API key and 30-second interval
faultray apm install --api-key sk_xxxx --interval 30

# Custom config directory
faultray apm install --config-dir /etc/faultray
```

---

## faultray apm start

Start the FaultRay APM agent.

```
faultray apm start [OPTIONS]
```

By default starts as a background daemon. Uses a PID file at the path configured in
`agent.yaml` (default: `~/.faultray/agent.pid`).

### Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--config` | `-f` | `~/.faultray/agent.yaml` | Path to agent config YAML |
| `--foreground` | `-F` | `false` | Run in foreground instead of background |

### Examples

```bash
# Start as background daemon
faultray apm start

# Start in foreground (useful for debugging)
faultray apm start --foreground

# Use a custom config file
faultray apm start --config /etc/faultray/agent.yaml
```

---

## faultray apm stop

Stop the running FaultRay APM agent.

```
faultray apm stop [OPTIONS]
```

Sends SIGTERM to the agent process and removes the PID file.

### Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--config` | `-f` | `~/.faultray/agent.yaml` | Path to agent config YAML |

### Examples

```bash
faultray apm stop
faultray apm stop --config /etc/faultray/agent.yaml
```

---

## faultray apm status

Show the status of the APM agent.

```
faultray apm status [OPTIONS]
```

Reads the PID file to determine if the agent is running, and shows configuration details
including agent ID, collector URL, and collection interval.

### Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--config` | `-f` | `~/.faultray/agent.yaml` | Path to agent config YAML |

### Examples

```bash
faultray apm status
faultray apm status --config /etc/faultray/agent.yaml
```

### Output

```
Agent is running (PID 12345)
  Agent ID:  a1b2c3d4-e5f6-7890-abcd-ef1234567890
  Collector: http://localhost:8080
  Interval:  15s
```

---

## faultray apm agents

List all registered APM agents.

```
faultray apm agents [OPTIONS]
```

Queries the FaultRay collector API (`GET /api/apm/agents`) for all known agents.

### Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--server` | `-s` | `http://localhost:8080` | FaultRay server URL |
| `--json` | | `false` | Output as JSON |

### Examples

```bash
faultray apm agents
faultray apm agents --server http://faultray:8080
faultray apm agents --json
```

### Output

```
          Registered APM Agents
┌──────────────┬────────────────────┬───────────────┬────────┬──────────────────────┬──────────────────────┐
│ Agent ID     │ Hostname           │ IP            │ Status │ Last Seen            │ OS                   │
├──────────────┼────────────────────┼───────────────┼────────┼──────────────────────┼──────────────────────┤
│ a1b2c3d4     │ prod-web-01        │ 10.0.1.10     │running │ 2026-03-31 12:34:56  │ Linux 6.6            │
└──────────────┴────────────────────┴───────────────┴────────┴──────────────────────┴──────────────────────┘
```

---

## faultray apm metrics

Query metrics for an APM agent.

```
faultray apm metrics AGENT_ID [OPTIONS]
```

Retrieves aggregated time-series metrics from the collector for the specified agent.

### Arguments

| Argument | Required | Description |
|---|---|---|
| `AGENT_ID` | Yes | Agent ID to query (from `faultray apm agents`) |

### Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--metric` | `-m` | all | Specific metric name to filter |
| `--server` | `-s` | `http://localhost:8080` | FaultRay server URL |
| `--json` | | `false` | Output as JSON |

### Available Metric Names

- `cpu_percent`
- `memory_percent`
- `disk_percent`
- `net_bytes_sent`
- `net_bytes_recv`
- `process_count`
- `tcp_connections`

### Examples

```bash
# All metrics for an agent
faultray apm metrics a1b2c3d4

# Single metric
faultray apm metrics a1b2c3d4 --metric cpu_percent

# JSON output
faultray apm metrics a1b2c3d4 --json

# Remote server
faultray apm metrics a1b2c3d4 --server http://faultray:8080
```

---

## faultray apm alerts

List APM alerts.

```
faultray apm alerts [OPTIONS]
```

Shows threshold-based alerts fired by the APM anomaly detection engine.
Alerts are classified as `critical`, `warning`, or `info`.

### Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--agent` | `-a` | all | Filter by agent ID |
| `--severity` | | all | Filter by severity (critical/warning/info) |
| `--server` | `-s` | `http://localhost:8080` | FaultRay server URL |
| `--json` | | `false` | Output as JSON |

### Examples

```bash
# All alerts
faultray apm alerts

# Critical alerts only
faultray apm alerts --severity critical

# Alerts for a specific agent
faultray apm alerts --agent a1b2c3d4

# JSON export
faultray apm alerts --json

# Combine filters
faultray apm alerts --agent a1b2c3d4 --severity warning
```

---

## faultray apm help

Show detailed APM help with architecture overview and all commands.

```
faultray apm help
```

Displays:
- ASCII architecture diagram (agent → collector → DB → anomaly detection)
- All APM commands with descriptions and examples
- Common workflows (setup, monitoring, alerting, chaos integration)
- Troubleshooting tips

**No flags.**

---

## Quick Reference

```bash
# First-time setup
faultray apm setup                          # Interactive wizard
faultray apm install -c http://host:8080    # Non-interactive
faultray apm start                          # Start daemon
faultray apm status                         # Verify running

# Day-to-day monitoring
faultray apm agents                         # See all agents
faultray apm metrics <id>                   # View metrics
faultray apm alerts                         # Check alerts
faultray apm alerts --severity critical     # Critical only

# Maintenance
faultray apm stop                           # Stop agent
faultray apm start --foreground             # Debug mode
```

---

## See Also

- [APM Quickstart Guide](../guides/apm-quickstart.md) — Step-by-step setup
- `faultray apm help` — Architecture overview in-terminal
- `faultray apm setup` — Interactive guided setup wizard
