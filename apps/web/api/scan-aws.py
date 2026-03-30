"""AWS infrastructure scanning endpoint.

POST /api/scan-aws
  Body: { "access_key_id": str, "secret_access_key": str, "region": str }
     or { "role_arn": str, "region": str }

Scans AWS infrastructure using boto3 and runs FaultRay simulation.
"""

from http.server import BaseHTTPRequestHandler
import json
import os


def _run_aws_scan(data: dict) -> dict:
    """Scan AWS infrastructure and run simulation."""
    import boto3
    from faultray.discovery.aws_scanner import AWSScanner
    from faultray.simulator.engine import SimulationEngine

    region = data.get("region", "us-east-1")
    role_arn = data.get("role_arn")
    access_key_id = data.get("access_key_id")
    secret_access_key = data.get("secret_access_key")

    # Set up AWS credentials via environment variables for boto3
    if role_arn:
        # AssumeRole flow
        sts = boto3.client(
            "sts",
            region_name=region,
            **(
                {
                    "aws_access_key_id": access_key_id,
                    "aws_secret_access_key": secret_access_key,
                }
                if access_key_id and secret_access_key
                else {}
            ),
        )
        assumed = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName="faultray-scan",
            DurationSeconds=900,
        )
        creds = assumed["Credentials"]
        os.environ["AWS_ACCESS_KEY_ID"] = creds["AccessKeyId"]
        os.environ["AWS_SECRET_ACCESS_KEY"] = creds["SecretAccessKey"]
        os.environ["AWS_SESSION_TOKEN"] = creds["SessionToken"]
    elif access_key_id and secret_access_key:
        os.environ["AWS_ACCESS_KEY_ID"] = access_key_id
        os.environ["AWS_SECRET_ACCESS_KEY"] = secret_access_key
        os.environ.pop("AWS_SESSION_TOKEN", None)
    else:
        raise ValueError(
            "Provide either access_key_id + secret_access_key, or role_arn"
        )

    try:
        scanner = AWSScanner(region=region)
        result = scanner.scan()
        graph = result.graph

        # Run simulation on discovered graph
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(
            include_feed=False, include_plugins=False
        )

        # Calculate availability nines from resilience score
        score = report.resilience_score
        if score >= 99.999:
            nines = 5.0
        elif score >= 99.99:
            nines = 4.0 + (score - 99.99) / 0.009
        elif score >= 99.9:
            nines = 3.0 + (score - 99.9) / 0.09
        elif score >= 99.0:
            nines = 2.0 + (score - 99.0) / 0.9
        elif score >= 90.0:
            nines = 1.0 + (score - 90.0) / 9.0
        else:
            nines = score / 90.0

        if nines >= 4.0:
            avail = "99.99%"
        elif nines >= 3.0:
            avail = "99.9%"
        elif nines >= 2.0:
            avail = "99%"
        else:
            avail = f"{score:.1f}%"

        critical_failures = []
        for r in report.critical_findings[:10]:
            critical_failures.append(
                {
                    "scenario": r.scenario.name,
                    "impact": (
                        f"Risk score {r.risk_score:.1f}/10 - "
                        f"{len(r.cascade.effects)} components affected"
                    ),
                    "severity": "CRITICAL" if r.risk_score >= 8.0 else "HIGH",
                }
            )

        suggestions = []
        seen: set[str] = set()
        for r in report.warnings[:10]:
            title = f"Harden: {r.scenario.name}"
            if title not in seen:
                seen.add(title)
                suggestions.append(
                    {
                        "title": title,
                        "description": (
                            f"Scenario risk score: {r.risk_score:.1f}. "
                            f"Consider adding redundancy or failover."
                        ),
                        "impact": f"+{(10 - r.risk_score) * 0.05:.1f} nines",
                        "effort": (
                            "Low" if r.risk_score < 5.0 else "Medium"
                        ),
                    }
                )

        return {
            "scan_summary": {
                "region": result.region,
                "components_found": result.components_found,
                "dependencies_inferred": result.dependencies_inferred,
                "scan_duration_seconds": round(
                    result.scan_duration_seconds, 2
                ),
                "warnings": result.warnings[:5],
            },
            "overall_score": round(score, 1),
            "availability_estimate": avail,
            "nines": round(nines, 2),
            "scenarios_passed": len(report.passed),
            "scenarios_failed": len(report.critical_findings),
            "total_scenarios": len(report.results),
            "layers": {
                "software": round(min(nines, 7.0), 2),
                "hardware": round(min(nines * 1.3, 7.0), 2),
                "theoretical": round(min(nines * 1.5, 7.0), 2),
            },
            "critical_failures": critical_failures,
            "suggestions": suggestions[:5],
        }
    finally:
        # Clean up credentials from environment
        os.environ.pop("AWS_ACCESS_KEY_ID", None)
        os.environ.pop("AWS_SECRET_ACCESS_KEY", None)
        os.environ.pop("AWS_SESSION_TOKEN", None)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body) if body else {}

            region = data.get("region")
            access_key_id = data.get("access_key_id")
            secret_access_key = data.get("secret_access_key")
            role_arn = data.get("role_arn")

            if not region:
                self._send_error(400, "Missing 'region' in request body")
                return

            if not role_arn and not (access_key_id and secret_access_key):
                self._send_error(
                    400,
                    "Provide 'access_key_id' + 'secret_access_key', "
                    "or 'role_arn'",
                )
                return

            result = _run_aws_scan(data)
            self._send_json(200, result)

        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON in request body")
        except Exception as e:
            error_type = type(e).__name__
            self._send_error(500, f"AWS scan error ({error_type}): {e}")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.send_header(
            "Access-Control-Allow-Methods", "POST, OPTIONS"
        )
        self.send_header(
            "Access-Control-Allow-Headers", "Content-Type, Authorization"
        )
        self.end_headers()

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _send_error(self, status: int, message: str):
        self._send_json(status, {"error": {"message": message}})

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
