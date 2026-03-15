# Slack Integration

FaultZero can send simulation results and alerts to Slack channels via webhooks or the Slack Bot integration.

## Webhook Setup

### 1. Create a Slack Incoming Webhook

1. Go to your Slack workspace settings
2. Navigate to **Apps > Incoming Webhooks**
3. Create a new webhook and select a channel
4. Copy the webhook URL

### 2. Configure FaultZero

```bash
export FAULTZERO_SLACK_WEBHOOK="https://hooks.slack.com/services/T.../B.../..."
```

Or in your configuration file:

```yaml
notifications:
  slack:
    webhook_url: "https://hooks.slack.com/services/T.../B.../..."
    channel: "#infrastructure"
    notify_on:
      - critical
      - score_change
```

### 3. Send results to Slack

```bash
faultzero simulate -m model.json --notify slack
```

## Notification Types

| Event | Description | Default |
|-------|-------------|---------|
| `critical` | Critical vulnerability detected | Enabled |
| `score_change` | Score changed by more than 5 points | Enabled |
| `simulation_complete` | Simulation finished | Disabled |
| `threshold_breach` | Score dropped below threshold | Enabled |

## Message Format

FaultZero sends rich Slack messages with:

- Resilience score with color-coded status
- Number of critical/warning findings
- Top 3 most impactful issues
- Link to the full HTML report (if hosted)

## Slack Bot (Advanced)

For interactive features, install the FaultZero Slack Bot:

```bash
faultzero slack-bot install --token xoxb-YOUR-BOT-TOKEN
```

Bot commands:

| Command | Description |
|---------|-------------|
| `/faultzero scan` | Trigger an infrastructure scan |
| `/faultzero score` | Show current resilience score |
| `/faultzero report` | Generate and share a report |
