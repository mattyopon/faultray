# CLI Commands

Complete reference for the FaultRay command-line interface.

## Global Options

```bash
faultray [OPTIONS] COMMAND [ARGS]
```

| Option | Description |
|--------|-------------|
| `--version` | Show version and exit |
| `--help` | Show help message and exit |
| `--verbose` / `-v` | Enable verbose output |
| `--quiet` / `-q` | Suppress non-essential output |

## Commands

### `quickstart`

Generate a sample infrastructure model and run a demo simulation.

```bash
faultray quickstart [--output MODEL_PATH]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--output` | `faultray-model.json` | Output path for the generated model |

### `scan`

Scan a live cloud environment and generate an infrastructure model.

```bash
faultray scan --provider PROVIDER [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--provider` | Cloud provider: `aws`, `gcp`, `azure`, `k8s` |
| `--output` / `-o` | Output file path |
| `--region` | Limit scan to a specific region |
| `--profile` | AWS profile name (AWS only) |

### `simulate`

Run failure simulations against an infrastructure model.

```bash
faultray simulate -m MODEL_PATH [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `-m` / `--model` | Required | Path to infrastructure model file |
| `--json` | `false` | Output results as JSON |
| `--scenarios` | `all` | Specific scenario set to run |
| `--cascade-depth` | `5` | Maximum cascade propagation depth |
| `--dynamic` | `false` | Enable dynamic simulation mode |

### `evaluate`

Evaluate resilience and produce a score summary.

```bash
faultray evaluate -m MODEL_PATH [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-m` / `--model` | Path to infrastructure model file |
| `--json` | Output results as JSON |
| `--threshold` | Minimum passing score (exits non-zero if below) |

### `report`

Generate an HTML resilience report.

```bash
faultray report -m MODEL_PATH -o OUTPUT_PATH [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-m` / `--model` | Path to infrastructure model file |
| `-o` / `--output` | Output HTML file path |
| `--format` | Report format: `html`, `pdf`, `json` |

### `tf-import`

Import infrastructure model from Terraform files.

```bash
faultray tf-import --dir TERRAFORM_DIR [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--dir` | Directory containing Terraform files |
| `--output` / `-o` | Output model file path |
| `--state` | Path to Terraform state file |

### `diff`

Compare two infrastructure models and show changes.

```bash
faultray diff MODEL_A MODEL_B [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--json` | Output diff as JSON |
| `--only-regressions` | Show only resilience regressions |

### `feed-update`

Update threat intelligence feeds for simulation scenarios.

```bash
faultray feed-update [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--source` | Feed source URL |
| `--force` | Force update even if cache is fresh |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Simulation found critical issues |
| 3 | Score below threshold (with `--threshold`) |
