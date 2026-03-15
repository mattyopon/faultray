# Quick Start

Get FaultZero up and running in under 5 minutes.

## Step 1: Install

```bash
pip install faultzero
```

## Step 2: Generate a sample model

The `quickstart` command creates a sample infrastructure model and runs a basic simulation:

```bash
faultzero quickstart
```

This generates an `infrasim-model.json` file in your current directory containing a sample multi-tier web application architecture.

## Step 3: Run a simulation

```bash
faultzero simulate -m infrasim-model.json
```

FaultZero will run 150+ failure scenarios against your model and produce a resilience report showing:

- Overall resilience score (0-100)
- Single points of failure (SPOFs)
- Cascade failure risks
- Availability ceiling estimates

## Step 4: View the report

Generate an HTML report for detailed visualization:

```bash
faultzero report -m infrasim-model.json -o report.html
```

Open `report.html` in your browser to see an interactive resilience dashboard.

## Step 5: Scan real infrastructure (optional)

If you have cloud credentials configured, scan your actual infrastructure:

```bash
# AWS
faultzero scan --provider aws --output my-infra.json

# Kubernetes
faultzero scan --provider k8s --output my-k8s.json

# Terraform
faultzero tf-import --dir ./terraform --output my-tf.json
```

## Next Steps

- [Your First Simulation](first-simulation.md) — Deep dive into simulation results
- [CLI Reference](../cli/commands.md) — Full command documentation
- [5-Layer Model](../concepts/five-layer-model.md) — Understand the infrastructure model
