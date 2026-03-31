# APM Quickstart Guide

FaultRay APM is a lightweight agent that collects real-time host metrics and sends them to the
FaultRay collector for anomaly detection, alerting, and topology-aware analysis.

---

## Prerequisites

- FaultRay installed: `pip install faultray`
- FaultRay server running (collector): `faultray serve`
- Python 3.11+ on each host you want to monitor

---

## Step-by-Step Setup

### 1. Start the Collector

The APM collector is built into the FaultRay web server. Start it on a host reachable by all
agents:

```bash
faultray serve
# Server starts at http://0.0.0.0:8080
```

### 2. Install the Agent (Interactive Wizard)

On each host you want to monitor, run the setup wizard:

```bash
faultray apm setup
```

The wizard will prompt for:
- Collector URL (e.g. `http://faultray-server:8080`)
- API key (optional)
- Collection interval (default: 15 seconds)

### 2b. Install the Agent (Non-Interactive)

For scripted deployments or CI/CD pipelines:

```bash
faultray apm install \
  --collector http://faultray-server:8080 \
  --api-key sk_xxxx \
  --interval 30
```

### 3. Start the Agent

```bash
# Background daemon (recommended for production)
faultray apm start

# Foreground (useful for debugging)
faultray apm start --foreground
```

### 4. Verify the Agent is Running

```bash
faultray apm status
```

Expected output:
```
Agent is running (PID 12345)
  Agent ID:  a1b2c3d4-...
  Collector: http://faultray-server:8080
  Interval:  15s
```

### 5. View Registered Agents

From any machine with access to the collector:

```bash
faultray apm agents
```

---

## Configuration Reference

The agent configuration file is stored at `~/.faultray/agent.yaml` by default.

| Field | Default | Description |
|---|---|---|
| `collector_url` | `http://localhost:8080` | FaultRay collector server URL |
| `api_key` | `""` | API key for authentication (optional) |
| `collect_interval_seconds` | `15` | How often to collect metrics |
| `pid_file` | `~/.faultray/agent.pid` | Path to PID file |
| `log_file` | `~/.faultray/agent.log` | Path to log file |
| `agent_id` | Auto-generated UUID | Unique agent identifier |

### Example agent.yaml

```yaml
agent_id: a1b2c3d4-e5f6-7890-abcd-ef1234567890
collector_url: http://faultray.internal:8080
api_key: sk_live_xxxx
collect_interval_seconds: 30
pid_file: /var/run/faultray/agent.pid
log_file: /var/log/faultray/agent.log
```

---

## Metrics Collected

Every collection cycle, the agent gathers the following metrics:

| Metric Name | Type | Description |
|---|---|---|
| `cpu_percent` | gauge | CPU utilization (%) across all cores |
| `memory_percent` | gauge | RAM usage (%) — used / total |
| `disk_percent` | gauge | Root disk usage (%) |
| `net_bytes_sent` | counter | Cumulative network bytes sent |
| `net_bytes_recv` | counter | Cumulative network bytes received |
| `process_count` | gauge | Number of running processes |
| `tcp_connections` | gauge | Number of active TCP connections |

---

## Alert Rules Configuration

Alert rules are evaluated server-side by the FaultRay anomaly detection engine.
Rules trigger when a metric crosses a threshold:

| Rule | Severity | Default Threshold |
|---|---|---|
| High CPU | warning | cpu_percent > 80% |
| Critical CPU | critical | cpu_percent > 95% |
| High Memory | warning | memory_percent > 85% |
| Critical Memory | critical | memory_percent > 95% |
| High Disk | warning | disk_percent > 80% |
| Critical Disk | critical | disk_percent > 90% |

View current alerts:

```bash
faultray apm alerts
faultray apm alerts --severity critical
faultray apm alerts --agent <agent-id>
faultray apm alerts --json
```

---

## Integration with Chaos Simulation

APM real-baseline data can inform your chaos simulation configuration:

### Capture a Baseline

```bash
# Export current metrics as JSON
faultray apm metrics <agent-id> --json > baseline-$(date +%Y%m%d).json
```

### Run a Simulation

```bash
faultray simulate infra.yaml
```

### Correlate Results

After a simulation run, check if APM detected any corresponding anomalies:

```bash
faultray apm alerts --severity warning
```

### Continuous Monitoring During Simulation

```bash
# Terminal 1: Run long simulation
faultray simulate infra.yaml --scenarios 5000

# Terminal 2: Watch APM alerts in real time
watch -n 5 faultray apm alerts
```

---

## Stopping the Agent

```bash
faultray apm stop
```

To verify the agent stopped:
```bash
faultray apm status
# Output: Agent is not running (no PID file)
```

---

## Troubleshooting

### Agent won't start — "already running" error

```bash
# Check if process is actually running
faultray apm status

# If not running but PID file exists, remove it
rm ~/.faultray/agent.pid

# Start again
faultray apm start
```

### No metrics appearing in dashboard

1. Verify the agent is running: `faultray apm status`
2. Check the collector URL matches what the agent is configured with
3. Ensure the collector (faultray serve) is reachable from the agent host
4. Check for firewall rules blocking port 8080

```bash
# Test connectivity from agent host
curl http://faultray-server:8080/api/apm/agents
```

### Agent exits immediately

Run in foreground to see the error:

```bash
faultray apm start --foreground
```

### High CPU usage from the agent

Increase the collection interval:

```bash
faultray apm install --interval 60
faultray apm stop
faultray apm start
```

### Connection refused / timeout

Ensure FaultRay server is running on the collector host:

```bash
# On the collector host
faultray serve
```

---

## See Also

- [CLI Reference](../cli/apm-commands.md) — All APM subcommands
- `faultray apm help` — Architecture overview and all commands in-terminal
- `faultray apm setup` — Interactive guided setup wizard
