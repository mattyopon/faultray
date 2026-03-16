"""Generate CI/CD resilience gate configurations.

Generates GitHub Actions, GitLab CI, and Jenkins pipeline configurations
that run FaultRay resilience checks as part of the CI/CD pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass

import yaml


@dataclass
class CIGateConfig:
    """Configuration for a CI/CD resilience gate."""

    min_resilience_score: int = 70
    max_critical_findings: int = 0
    max_spof_count: int = 0
    fail_on_regression: bool = True
    infrastructure_file: str = "infrastructure.yaml"
    output_format: str = "json"  # json, markdown, or sarif
    notify_slack: bool = False
    slack_webhook: str = ""


class CIGateGenerator:
    """Generate CI/CD pipeline configurations for resilience gates."""

    def generate_github_action(self, config: CIGateConfig) -> str:
        """Generate a .github/workflows/resilience-gate.yml workflow.

        Parameters
        ----------
        config:
            Gate configuration controlling thresholds and behavior.

        Returns
        -------
        str
            Complete YAML content for a GitHub Actions workflow file.
        """
        workflow: dict = {
            "name": "FaultRay Resilience Gate",
            "on": {
                "pull_request": {
                    "paths": [
                        "**/*.yaml",
                        "**/*.yml",
                        "**/*.tf",
                        "**/infrastructure/**",
                    ],
                },
                "push": {
                    "branches": ["main"],
                },
                "workflow_dispatch": {
                    "inputs": {
                        "min_score": {
                            "description": "Minimum resilience score (0-100)",
                            "required": False,
                            "default": str(config.min_resilience_score),
                            "type": "string",
                        },
                        "infrastructure_file": {
                            "description": "Path to infrastructure YAML file",
                            "required": False,
                            "default": config.infrastructure_file,
                            "type": "string",
                        },
                    },
                },
            },
            "env": {
                "MIN_SCORE": str(config.min_resilience_score),
                "MAX_CRITICAL": str(config.max_critical_findings),
                "MAX_SPOF": str(config.max_spof_count),
                "INFRA_FILE": config.infrastructure_file,
            },
            "jobs": {
                "resilience-check": self._build_resilience_job(config),
            },
        }

        return yaml.dump(workflow, default_flow_style=False, sort_keys=False, width=120)

    def _build_resilience_job(self, config: CIGateConfig) -> dict:
        """Build the resilience-check job definition."""
        steps = [
            {"uses": "actions/checkout@v4"},
            {
                "uses": "actions/setup-python@v5",
                "with": {"python-version": "3.12"},
            },
            {
                "name": "Install FaultRay",
                "run": "pip install faultray",
            },
            {
                "name": "Run Resilience Analysis",
                "id": "resilience",
                "run": self._build_analysis_script(config),
            },
            {
                "name": "Generate SARIF Report",
                "if": "always()",
                "run": self._build_sarif_script(config),
            },
        ]

        # PR comment step
        steps.append({
            "name": "Post PR Comment",
            "if": "github.event_name == 'pull_request' && always()",
            "uses": "actions/github-script@v7",
            "with": {
                "script": self._build_pr_comment_script(),
            },
        })

        # SARIF upload step
        steps.append({
            "name": "Upload SARIF",
            "if": "always() && hashFiles('results.sarif') != ''",
            "uses": "github/codeql-action/upload-sarif@v3",
            "with": {
                "sarif_file": "results.sarif",
            },
        })

        # Slack notification step
        if config.notify_slack:
            steps.append({
                "name": "Notify Slack",
                "if": "always()",
                "run": self._build_slack_script(config),
                "env": {
                    "SLACK_WEBHOOK": "${{ secrets.SLACK_WEBHOOK }}"
                    if not config.slack_webhook
                    else config.slack_webhook,
                },
            })

        # Regression check step
        if config.fail_on_regression:
            steps.append({
                "name": "Check for Regression",
                "run": self._build_regression_script(),
            })

        # Upload baseline artifact
        steps.append({
            "name": "Upload Baseline Artifact",
            "if": "github.event_name == 'push' && github.ref == 'refs/heads/main'",
            "uses": "actions/upload-artifact@v4",
            "with": {
                "name": "resilience-baseline",
                "path": "results.json",
                "retention-days": "90",
            },
        })

        return {
            "runs-on": "ubuntu-latest",
            "permissions": {
                "contents": "read",
                "pull-requests": "write",
                "security-events": "write",
            },
            "steps": steps,
        }

    def _build_analysis_script(self, config: CIGateConfig) -> str:
        """Build the shell script for resilience analysis."""
        lines = [
            "set -euo pipefail",
            "",
            "# Use workflow_dispatch inputs if available, otherwise use env defaults",
            'INFRA_FILE="${{ github.event.inputs.infrastructure_file || env.INFRA_FILE }}"',
            'MIN_SCORE="${{ github.event.inputs.min_score || env.MIN_SCORE }}"',
            "",
            '# Verify infrastructure file exists',
            'if [ ! -f "$INFRA_FILE" ]; then',
            '  echo "::error::Infrastructure file not found: $INFRA_FILE"',
            '  exit 1',
            'fi',
            "",
            "# Run FaultRay simulation",
            'faultray simulate --model "$INFRA_FILE" --json > results.json',
            "",
            "# Extract metrics",
            "SCORE=$(python3 -c \"import json; print(json.load(open('results.json')).get('resilience_score', 0))\")",
            "CRITICAL=$(python3 -c \"import json; print(json.load(open('results.json')).get('critical', 0))\")",
            "WARNING=$(python3 -c \"import json; print(json.load(open('results.json')).get('warning', 0))\")",
            "PASSED=$(python3 -c \"import json; print(json.load(open('results.json')).get('passed', 0))\")",
            "",
            '# Set outputs',
            'echo "resilience_score=$SCORE" >> $GITHUB_OUTPUT',
            'echo "critical_count=$CRITICAL" >> $GITHUB_OUTPUT',
            'echo "warning_count=$WARNING" >> $GITHUB_OUTPUT',
            'echo "passed_count=$PASSED" >> $GITHUB_OUTPUT',
            "",
            "# Check thresholds",
            'FAILED=0',
            "",
            'if [ "$(echo "$SCORE < $MIN_SCORE" | bc -l)" -eq 1 ]; then',
            '  echo "::error::Resilience score $SCORE is below minimum $MIN_SCORE"',
            '  FAILED=1',
            'fi',
            "",
            f'if [ "$CRITICAL" -gt {config.max_critical_findings} ]; then',
            f'  echo "::error::$CRITICAL critical findings exceed maximum {config.max_critical_findings}"',
            '  FAILED=1',
            'fi',
            "",
            'if [ "$FAILED" -eq 1 ]; then',
            '  exit 1',
            'fi',
            "",
            'echo "Resilience gate passed: score=$SCORE, critical=$CRITICAL"',
        ]
        return "\n".join(lines)

    def _build_sarif_script(self, config: CIGateConfig) -> str:
        """Build the shell script for SARIF report generation."""
        lines = [
            "set -euo pipefail",
            "",
            '# Generate SARIF report from results',
            'python3 -c "',
            "import json",
            "from faultray.ci.sarif_exporter import SARIFExporter",
            "results = json.load(open('results.json'))",
            "sarif = SARIFExporter.from_json_results(results)",
            "with open('results.sarif', 'w') as f:",
            "    json.dump(sarif, f, indent=2)",
            '"',
        ]
        return "\n".join(lines)

    def _build_pr_comment_script(self) -> str:
        """Build the GitHub Script for posting PR comments."""
        return """const fs = require('fs');
const results = JSON.parse(fs.readFileSync('results.json', 'utf8'));
const score = results.resilience_score || 0;
const critical = results.critical || 0;
const warning = results.warning || 0;
const passed = results.passed || 0;
const total = results.total_scenarios || 0;

const scoreEmoji = score >= 80 ? '\\u2705' : score >= 60 ? '\\u26a0\\ufe0f' : '\\u274c';
const statusText = critical === 0 ? 'PASSED' : 'FAILED';
const statusEmoji = critical === 0 ? '\\u2705' : '\\u274c';

const body = `## ${statusEmoji} FaultRay Resilience Gate: ${statusText}

| Metric | Value |
|--------|-------|
| ${scoreEmoji} Resilience Score | **${score}/100** |
| Critical Findings | ${critical} |
| Warnings | ${warning} |
| Passed Scenarios | ${passed}/${total} |

<details>
<summary>View detailed results</summary>

\\`\\`\\`json
${JSON.stringify(results, null, 2).substring(0, 3000)}
\\`\\`\\`

</details>

---
*Generated by [FaultRay](https://github.com/faultray/faultray) Resilience Gate*`;

// Find and update existing comment or create new one
const { data: comments } = await github.rest.issues.listComments({
  owner: context.repo.owner,
  repo: context.repo.repo,
  issue_number: context.issue.number,
});

const botComment = comments.find(c =>
  c.body.includes('FaultRay Resilience Gate')
);

if (botComment) {
  await github.rest.issues.updateComment({
    owner: context.repo.owner,
    repo: context.repo.repo,
    comment_id: botComment.id,
    body: body,
  });
} else {
  await github.rest.issues.createComment({
    owner: context.repo.owner,
    repo: context.repo.repo,
    issue_number: context.issue.number,
    body: body,
  });
}"""

    def _build_slack_script(self, config: CIGateConfig) -> str:
        """Build the shell script for Slack notifications."""
        lines = [
            "set -euo pipefail",
            "",
            "SCORE=$(python3 -c \"import json; print(json.load(open('results.json')).get('resilience_score', 0))\")",
            "CRITICAL=$(python3 -c \"import json; print(json.load(open('results.json')).get('critical', 0))\")",
            "",
            'if [ "$CRITICAL" -gt 0 ]; then',
            '  STATUS="FAILED"',
            '  COLOR="#dc3545"',
            'else',
            '  STATUS="PASSED"',
            '  COLOR="#28a745"',
            'fi',
            "",
            "curl -s -X POST \"$SLACK_WEBHOOK\" \\",
            "  -H 'Content-Type: application/json' \\",
            "  -d \"{",
            '    \\\"attachments\\\": [{',
            '      \\\"color\\\": \\\"$COLOR\\\",',
            '      \\\"title\\\": \\\"FaultRay Resilience Gate: $STATUS\\\",',
            '      \\\"text\\\": \\\"Score: $SCORE/100 | Critical: $CRITICAL\\\",',
            '      \\\"footer\\\": \\\"${{ github.repository }} @ ${{ github.sha }}\\\"',
            "    }]",
            '  }"',
        ]
        return "\n".join(lines)

    def _build_regression_script(self) -> str:
        """Build the shell script for regression detection."""
        lines = [
            "set -euo pipefail",
            "",
            "# Download previous baseline if available",
            "# This uses the artifact from the last main branch push",
            'if [ -f "baseline.json" ]; then',
            "  PREV_SCORE=$(python3 -c \"import json; print(json.load(open('baseline.json')).get('resilience_score', 0))\")",
            "  CURR_SCORE=$(python3 -c \"import json; print(json.load(open('results.json')).get('resilience_score', 0))\")",
            "",
            '  if [ "$(echo "$CURR_SCORE < $PREV_SCORE" | bc -l)" -eq 1 ]; then',
            '    echo "::error::Resilience regression detected: $CURR_SCORE < $PREV_SCORE (previous baseline)"',
            '    exit 1',
            '  fi',
            '  echo "No regression: $CURR_SCORE >= $PREV_SCORE"',
            'else',
            '  echo "No baseline found, skipping regression check"',
            'fi',
        ]
        return "\n".join(lines)

    def generate_gitlab_ci(self, config: CIGateConfig) -> str:
        """Generate a .gitlab-ci.yml snippet for resilience gate.

        Parameters
        ----------
        config:
            Gate configuration controlling thresholds and behavior.

        Returns
        -------
        str
            YAML content for a GitLab CI job.
        """
        job: dict = {
            "resilience-gate": {
                "stage": "test",
                "image": "python:3.12-slim",
                "before_script": [
                    "pip install faultray",
                ],
                "script": [
                    f"faultray simulate --model {config.infrastructure_file} --json > results.json",
                    "SCORE=$(python3 -c \"import json; print(json.load(open('results.json')).get('resilience_score', 0))\")",
                    "CRITICAL=$(python3 -c \"import json; print(json.load(open('results.json')).get('critical', 0))\")",
                    f'if [ "$(echo "$SCORE < {config.min_resilience_score}" | bc -l)" -eq 1 ]; then '
                    f'echo "Resilience score $SCORE is below minimum {config.min_resilience_score}"; exit 1; fi',
                    f'if [ "$CRITICAL" -gt {config.max_critical_findings} ]; then '
                    f'echo "$CRITICAL critical findings exceed maximum {config.max_critical_findings}"; exit 1; fi',
                    'echo "Resilience gate passed: score=$SCORE, critical=$CRITICAL"',
                ],
                "artifacts": {
                    "paths": ["results.json"],
                    "when": "always",
                    "expire_in": "30 days",
                },
                "rules": [
                    {"changes": ["**/*.yaml", "**/*.yml", "**/*.tf", "**/infrastructure/**"]},
                ],
            },
        }

        return yaml.dump(job, default_flow_style=False, sort_keys=False, width=120)

    def generate_jenkins(self, config: CIGateConfig) -> str:
        """Generate a Jenkinsfile stage for resilience gate.

        Parameters
        ----------
        config:
            Gate configuration controlling thresholds and behavior.

        Returns
        -------
        str
            Groovy content for a Jenkins pipeline stage.
        """
        lines = [
            "stage('Resilience Gate') {",
            "    steps {",
            "        sh 'pip install faultray'",
            f"        sh 'faultray simulate --model {config.infrastructure_file} --json > results.json'",
            "        script {",
            "            def results = readJSON file: 'results.json'",
            f"            def minScore = {config.min_resilience_score}",
            f"            def maxCritical = {config.max_critical_findings}",
            "            def score = results.resilience_score ?: 0",
            "            def critical = results.critical ?: 0",
            "",
            "            echo \"Resilience Score: ${score}/100\"",
            "            echo \"Critical Findings: ${critical}\"",
            "",
            "            if (score < minScore) {",
            "                error \"Resilience score ${score} is below minimum ${minScore}\"",
            "            }",
            "            if (critical > maxCritical) {",
            "                error \"${critical} critical findings exceed maximum ${maxCritical}\"",
            "            }",
            "",
            "            echo 'Resilience gate passed'",
            "        }",
            "    }",
            "    post {",
            "        always {",
            "            archiveArtifacts artifacts: 'results.json', allowEmptyArchive: true",
            "        }",
            "    }",
            "}",
        ]
        return "\n".join(lines)
