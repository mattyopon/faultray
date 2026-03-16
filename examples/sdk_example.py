"""Example: Using FaultZero Python SDK.

Demonstrates all major SDK features including loading infrastructure,
running simulations, SLA validation, genome analysis, benchmarking,
natural language queries, environment comparison, and exports.
"""

from faultray import FaultZero

# ============================================================
# 1. Quick Start - Load from demo infrastructure
# ============================================================
print("=" * 60)
print("1. Quick Start with Demo Infrastructure")
print("=" * 60)

fz = FaultZero.demo()
print(fz)
print()

# ============================================================
# 2. Basic Properties
# ============================================================
print("=" * 60)
print("2. Basic Properties")
print("=" * 60)

print(f"  Resilience Score: {fz.resilience_score}/100")
print(f"  Components:       {fz.component_count}")
print(f"  SPOFs:            {fz.spof_count}")
print()

for comp in fz.components:
    print(f"  [{comp.type.value}] {comp.name} (replicas={comp.replicas})")
print()

# ============================================================
# 3. Run Simulation
# ============================================================
print("=" * 60)
print("3. Chaos Simulation")
print("=" * 60)

report = fz.simulate(include_feed=False)
print(f"  Total scenarios:  {len(report.results)}")
print(f"  Critical:         {len(report.critical_findings)}")
print(f"  Warnings:         {len(report.warnings)}")
print(f"  Passed:           {len(report.passed)}")
print()

if report.critical_findings:
    print("  Top 3 Critical Findings:")
    for finding in report.critical_findings[:3]:
        print(f"    - {finding.scenario.name} (risk={finding.risk_score:.1f})")
    print()

# ============================================================
# 4. SLA Validation
# ============================================================
print("=" * 60)
print("4. SLA Validation")
print("=" * 60)

for nines in [3.0, 4.0, 5.0]:
    sla = fz.validate_sla(target_nines=nines)
    status = "ACHIEVABLE" if sla.achievable else "NOT ACHIEVABLE"
    print(f"  {nines} nines ({sla.target.target_percent:.4f}%): {status}")
    print(f"    Estimated availability: {sla.calculated_availability*100:.4f}%")
    print(f"    Allowed downtime:       {sla.allowed_downtime}")
    print(f"    Estimated downtime:     {sla.estimated_downtime}")
print()

# ============================================================
# 5. Genome (Infrastructure DNA)
# ============================================================
print("=" * 60)
print("5. Resilience Genome")
print("=" * 60)

genome = fz.genome()
print(f"  Grade:        {genome.resilience_grade}")
print(f"  Architecture: {genome.structural_age}")
print(f"  Percentile:   {genome.benchmark_percentile:.0f}th")
if genome.weakness_genes:
    print(f"  Weaknesses:   {', '.join(genome.weakness_genes[:3])}")
print()

# ============================================================
# 6. Industry Benchmarking
# ============================================================
print("=" * 60)
print("6. Industry Benchmark (SaaS)")
print("=" * 60)

bench = fz.benchmark(industry="saas")
print(f"  Your score:    {bench.your_score:.1f}")
print(f"  Percentile:    {bench.percentile:.0f}th")
print(f"  Rank:          {bench.rank_description}")
if bench.strengths:
    print(f"  Strengths:     {bench.strengths[0]}")
if bench.weaknesses:
    print(f"  Top weakness:  {bench.weaknesses[0]}")
print()

# ============================================================
# 7. Risk Heatmap
# ============================================================
print("=" * 60)
print("7. Risk Heatmap")
print("=" * 60)

heatmap = fz.risk_heatmap()
print(f"  Components analyzed: {len(heatmap.components)}")
print(f"  Hotspots:            {len(heatmap.hotspots)}")
for hotspot in heatmap.hotspots[:3]:
    print(f"    - {hotspot.component_id}: risk={hotspot.overall_risk:.2f}")
print()

# ============================================================
# 8. Find SPOFs and Quick Wins
# ============================================================
print("=" * 60)
print("8. SPOFs and Quick Wins")
print("=" * 60)

spofs = fz.find_spofs()
print(f"  SPOFs found: {len(spofs)}")
for spof in spofs:
    print(f"    - {spof.name} ({spof.type.value})")

wins = fz.quick_wins()
print(f"\n  Quick wins: {len(wins)}")
for win in wins[:3]:
    print(f"    - {win.description}")
print()

# ============================================================
# 9. Incident Replay
# ============================================================
print("=" * 60)
print("9. Incident Replay")
print("=" * 60)

replays = fz.replay_all_incidents()
print(f"  Incidents replayed: {len(replays)}")
for r in replays[:3]:
    status = "SURVIVED" if r.survived else "FAILED"
    print(f"    [{status}] {r.incident.name} (impact={r.impact_score:.1f})")
print()

# ============================================================
# 10. Natural Language Chat
# ============================================================
print("=" * 60)
print("10. Natural Language Queries")
print("=" * 60)

questions = [
    "What happens if the database goes down?",
    "How resilient is the system?",
    "What are the risks?",
]
for q in questions:
    answer = fz.chat(q)
    # Truncate long answers for display
    short = answer[:120] + "..." if len(answer) > 120 else answer
    print(f"  Q: {q}")
    print(f"  A: {short}")
    print()

# ============================================================
# 11. Export Formats
# ============================================================
print("=" * 60)
print("11. Export Formats")
print("=" * 60)

# YAML
yaml_str = fz.to_yaml()
print(f"  YAML export: {len(yaml_str)} bytes")

# JSON
json_str = fz.to_json()
print(f"  JSON export: {len(json_str)} bytes")

# Mermaid diagram
mermaid = fz.to_mermaid()
print(f"  Mermaid diagram: {len(mermaid)} bytes")
print(f"  Preview:\n    {mermaid[:200]}...")

# Terraform
tf_files = fz.to_terraform()
print(f"  Terraform files: {len(tf_files)}")
for path in list(tf_files.keys())[:3]:
    print(f"    - {path}")
print()

# ============================================================
# 12. Natural Language Infrastructure Creation
# ============================================================
print("=" * 60)
print("12. Create from Natural Language")
print("=" * 60)

fz2 = FaultZero.from_text("3 web servers behind ALB with Aurora database and Redis cache")
print(f"  Components: {fz2.component_count}")
print(f"  Score:      {fz2.resilience_score}/100")
for comp in fz2.components:
    print(f"    [{comp.type.value}] {comp.name}")
print()

# ============================================================
# 13. Dictionary-based Creation
# ============================================================
print("=" * 60)
print("13. Create from Dictionary")
print("=" * 60)

data = {
    "components": [
        {"id": "lb", "name": "Load Balancer", "type": "load_balancer", "replicas": 2},
        {"id": "api", "name": "API Server", "type": "app_server", "replicas": 3},
        {"id": "db", "name": "Database", "type": "database", "replicas": 1},
    ],
    "dependencies": [
        {"source_id": "lb", "target_id": "api", "dependency_type": "requires"},
        {"source_id": "api", "target_id": "db", "dependency_type": "requires"},
    ],
}

fz3 = FaultZero.from_dict(data)
print(f"  Components: {fz3.component_count}")
print(f"  Score:      {fz3.resilience_score}/100")
print(f"  SPOFs:      {fz3.spof_count}")
print()

# ============================================================
# Done
# ============================================================
print("=" * 60)
print("SDK Example Complete!")
print("=" * 60)
