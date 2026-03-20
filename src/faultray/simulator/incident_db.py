# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Historical incident database for the Incident Replay Engine.

Contains documented real-world cloud and infrastructure outages with accurate
dates, durations, root causes, and affected services. These incidents can be
replayed against any infrastructure topology to assess resilience.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from faultray.simulator.incident_replay import HistoricalIncident, IncidentEvent

HISTORICAL_INCIDENTS: list[HistoricalIncident] = [
    # -----------------------------------------------------------------------
    # 1. AWS us-east-1 Major Outage (Dec 2021)
    # -----------------------------------------------------------------------
    HistoricalIncident(
        id="aws-us-east-1-2021-12",
        name="AWS us-east-1 Major Outage (Dec 2021)",
        provider="aws",
        date=datetime(2021, 12, 7),
        duration=timedelta(hours=11),
        root_cause=(
            "Automated scaling activity in the internal network triggered "
            "unexpected behavior, causing network device exhaustion in "
            "us-east-1. The internal network that connects services was "
            "overwhelmed, impacting multiple AWS services."
        ),
        affected_services=["ec2", "rds", "elasticache", "lambda", "sqs", "cloudwatch", "ecs"],
        affected_regions=["us-east-1"],
        severity="critical",
        timeline=[
            IncidentEvent(
                timestamp_offset=timedelta(minutes=0),
                event_type="service_degradation",
                affected_services=["ec2", "cloudwatch"],
                description="Initial network congestion detected in us-east-1",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(minutes=30),
                event_type="full_outage",
                affected_services=["ec2", "rds", "elasticache", "lambda", "sqs"],
                description="Multiple services experience API errors and connectivity issues",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=3),
                event_type="service_degradation",
                affected_services=["ec2", "rds"],
                description="AWS begins internal network recovery procedures",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=7),
                event_type="partial_recovery",
                affected_services=["ec2", "lambda"],
                description="EC2 and Lambda begin recovering, new instances launching",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=11),
                event_type="full_recovery",
                affected_services=["ec2", "rds", "elasticache", "lambda", "sqs", "cloudwatch"],
                description="All services fully recovered in us-east-1",
            ),
        ],
        lessons_learned=[
            "Multi-region architecture is essential for critical workloads",
            "Control plane dependencies can cause cascading failures across services",
            "AWS internal networking is a shared dependency across many services",
            "Monitor and test failover to secondary regions regularly",
        ],
        post_mortem_url="https://aws.amazon.com/message/12721/",
        tags=["network", "control-plane", "multi-service", "us-east-1"],
    ),

    # -----------------------------------------------------------------------
    # 2. AWS S3 us-east-1 Outage (Feb 2017)
    # -----------------------------------------------------------------------
    HistoricalIncident(
        id="aws-s3-2017-02",
        name="AWS S3 us-east-1 Outage (Feb 2017)",
        provider="aws",
        date=datetime(2017, 2, 28),
        duration=timedelta(hours=5),
        root_cause=(
            "An authorized S3 team member executed a command to remove a small "
            "number of servers for an S3 subsystem but incorrectly entered a "
            "larger set of servers than intended. The removed servers supported "
            "critical S3 metadata services."
        ),
        affected_services=["s3", "ec2", "lambda", "sqs"],
        affected_regions=["us-east-1"],
        severity="critical",
        timeline=[
            IncidentEvent(
                timestamp_offset=timedelta(minutes=0),
                event_type="full_outage",
                affected_services=["s3"],
                description="S3 PUT/GET requests begin failing in us-east-1",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(minutes=15),
                event_type="full_outage",
                affected_services=["s3", "ec2", "lambda"],
                description="Cascading impact: services depending on S3 begin failing",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=3),
                event_type="partial_recovery",
                affected_services=["s3"],
                description="S3 subsystem index rebuild begins showing progress",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=5),
                event_type="full_recovery",
                affected_services=["s3", "ec2", "lambda", "sqs"],
                description="Full service restoration",
            ),
        ],
        lessons_learned=[
            "Operator error safeguards are critical for production operations",
            "S3 is a foundational dependency for many AWS services",
            "The internet's reliance on S3 was underestimated",
            "Rate-limit tooling to prevent large-scale accidental removals",
        ],
        post_mortem_url="https://aws.amazon.com/message/41926/",
        tags=["human-error", "storage", "cascading", "us-east-1"],
    ),

    # -----------------------------------------------------------------------
    # 3. Facebook/Meta Global BGP Outage (Oct 2021)
    # -----------------------------------------------------------------------
    HistoricalIncident(
        id="meta-bgp-2021-10",
        name="Facebook/Meta Global BGP Outage (Oct 2021)",
        provider="generic",
        date=datetime(2021, 10, 4),
        duration=timedelta(hours=6),
        root_cause=(
            "A routine BGP configuration change during planned maintenance "
            "inadvertently withdrew all BGP route advertisements for Facebook's "
            "DNS nameservers and infrastructure. This made Facebook, Instagram, "
            "WhatsApp, and internal tools completely unreachable."
        ),
        affected_services=["dns", "cdn"],
        affected_regions=["global"],
        severity="critical",
        timeline=[
            IncidentEvent(
                timestamp_offset=timedelta(minutes=0),
                event_type="full_outage",
                affected_services=["dns"],
                description="BGP routes withdrawn; DNS resolution fails globally",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(minutes=5),
                event_type="full_outage",
                affected_services=["dns", "cdn"],
                description="All Facebook properties unreachable worldwide",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=4),
                event_type="partial_recovery",
                affected_services=["dns"],
                description="Engineers gain physical access to data centers to fix BGP",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=6),
                event_type="full_recovery",
                affected_services=["dns", "cdn"],
                description="BGP routes re-advertised, services gradually return",
            ),
        ],
        lessons_learned=[
            "BGP configuration changes need robust rollback mechanisms",
            "Out-of-band access to infrastructure is critical for disaster recovery",
            "DNS is a single point of failure that can take down everything",
            "Internal tools should not depend on the same infrastructure as production",
        ],
        post_mortem_url="https://engineering.fb.com/2021/10/05/networking-traffic/outage-details/",
        tags=["bgp", "dns", "global", "configuration-error"],
    ),

    # -----------------------------------------------------------------------
    # 4. Cloudflare Major Outage (Jun 2022)
    # -----------------------------------------------------------------------
    HistoricalIncident(
        id="cloudflare-2022-06",
        name="Cloudflare Major Outage (Jun 2022)",
        provider="cloudflare",
        date=datetime(2022, 6, 21),
        duration=timedelta(hours=2),
        root_cause=(
            "A network configuration change as part of a long-running project "
            "to increase resilience in Cloudflare's busiest locations caused "
            "a BGP routing issue. A change to the BGP configuration in 19 data "
            "centers caused an outage across those locations."
        ),
        affected_services=["cdn", "dns", "api_gateway"],
        affected_regions=["global"],
        severity="major",
        timeline=[
            IncidentEvent(
                timestamp_offset=timedelta(minutes=0),
                event_type="service_degradation",
                affected_services=["cdn"],
                description="Traffic routing issues detected in multiple PoPs",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(minutes=10),
                event_type="full_outage",
                affected_services=["cdn", "dns", "api_gateway"],
                description="19 data centers impacted, ~50% of requests affected",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=1),
                event_type="partial_recovery",
                affected_services=["cdn", "dns"],
                description="Configuration rollback underway, PoPs recovering",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=2),
                event_type="full_recovery",
                affected_services=["cdn", "dns", "api_gateway"],
                description="All data centers fully recovered",
            ),
        ],
        lessons_learned=[
            "Staged rollout of network changes across data centers",
            "Canary deployments for infrastructure changes",
            "Automated rollback for BGP changes",
        ],
        post_mortem_url="https://blog.cloudflare.com/cloudflare-outage-on-june-21-2022/",
        tags=["bgp", "cdn", "configuration-error", "network"],
    ),

    # -----------------------------------------------------------------------
    # 5. Google Cloud Networking Outage (Jun 2019)
    # -----------------------------------------------------------------------
    HistoricalIncident(
        id="gcp-2019-06",
        name="Google Cloud Networking Outage (Jun 2019)",
        provider="gcp",
        date=datetime(2019, 6, 2),
        duration=timedelta(hours=4, minutes=25),
        root_cause=(
            "A configuration change intended for a small number of servers in "
            "a single region was incorrectly applied to a larger number of "
            "servers across several neighboring regions. This caused high "
            "network congestion and packet loss."
        ),
        affected_services=["compute_engine", "cloud_sql", "gcs"],
        affected_regions=["us-central1", "us-east1", "us-east4", "us-west2",
                          "northamerica-northeast1", "southamerica-east1"],
        severity="critical",
        timeline=[
            IncidentEvent(
                timestamp_offset=timedelta(minutes=0),
                event_type="service_degradation",
                affected_services=["compute_engine"],
                description="Network congestion causes elevated packet loss",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(minutes=20),
                event_type="full_outage",
                affected_services=["compute_engine", "cloud_sql", "gcs"],
                description="Multiple regions severely impacted, services unavailable",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=2),
                event_type="partial_recovery",
                affected_services=["compute_engine"],
                description="Configuration rolled back, congestion decreasing",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=4, minutes=25),
                event_type="full_recovery",
                affected_services=["compute_engine", "cloud_sql", "gcs"],
                description="Full recovery across all affected regions",
            ),
        ],
        lessons_learned=[
            "Configuration changes must have blast radius limits",
            "Multi-region does not help if the outage spans multiple regions",
            "Network changes should have automated canary testing",
        ],
        post_mortem_url="https://status.cloud.google.com/incident/cloud-networking/19009",
        tags=["network", "configuration-error", "multi-region"],
    ),

    # -----------------------------------------------------------------------
    # 6. Azure WAN Routing Outage (Jan 2023)
    # -----------------------------------------------------------------------
    HistoricalIncident(
        id="azure-2023-01",
        name="Azure WAN Routing Outage (Jan 2023)",
        provider="azure",
        date=datetime(2023, 1, 25),
        duration=timedelta(hours=9),
        root_cause=(
            "A Wide Area Network (WAN) routing change impacted connectivity "
            "between Azure regions and to the internet. A command run to update "
            "the WAN network caused an unexpected side effect that resulted in "
            "widespread packet loss."
        ),
        affected_services=["azure_vm", "azure_sql", "azure_storage", "azure_lb"],
        affected_regions=["global"],
        severity="critical",
        timeline=[
            IncidentEvent(
                timestamp_offset=timedelta(minutes=0),
                event_type="service_degradation",
                affected_services=["azure_vm"],
                description="WAN routing change triggers connectivity issues",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(minutes=15),
                event_type="full_outage",
                affected_services=["azure_vm", "azure_sql", "azure_storage", "azure_lb"],
                description="Global Azure services impacted, Microsoft 365 affected",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=5),
                event_type="partial_recovery",
                affected_services=["azure_vm", "azure_lb"],
                description="WAN changes reverted, services gradually recovering",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=9),
                event_type="full_recovery",
                affected_services=["azure_vm", "azure_sql", "azure_storage", "azure_lb"],
                description="Full service restoration globally",
            ),
        ],
        lessons_learned=[
            "WAN changes require phased rollout with automatic rollback",
            "Multi-cloud strategy protects against single provider outages",
            "Core networking changes should have smaller blast radius",
        ],
        post_mortem_url="https://azure.status.microsoft/en-us/status/history/",
        tags=["wan", "network", "global", "routing"],
    ),

    # -----------------------------------------------------------------------
    # 7. GitHub 1.35 Tbps DDoS Attack (Feb 2018)
    # -----------------------------------------------------------------------
    HistoricalIncident(
        id="github-ddos-2018",
        name="GitHub 1.35 Tbps DDoS Attack (Feb 2018)",
        provider="generic",
        date=datetime(2018, 2, 28),
        duration=timedelta(minutes=20),
        root_cause=(
            "Memcached amplification DDoS attack that peaked at 1.35 Tbps. "
            "Attackers exploited exposed memcached servers to amplify traffic "
            "by a factor of 51,000x. GitHub's DDoS mitigation provider "
            "(Akamai Prolexic) successfully mitigated the attack."
        ),
        affected_services=["cdn", "load_balancer", "server"],
        affected_regions=["global"],
        severity="major",
        timeline=[
            IncidentEvent(
                timestamp_offset=timedelta(minutes=0),
                event_type="full_outage",
                affected_services=["cdn", "load_balancer"],
                description="1.35 Tbps DDoS attack overwhelms GitHub's edge",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(minutes=8),
                event_type="service_degradation",
                affected_services=["cdn", "load_balancer"],
                description="Traffic rerouted to Akamai Prolexic scrubbing centers",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(minutes=20),
                event_type="full_recovery",
                affected_services=["cdn", "load_balancer", "server"],
                description="Attack mitigated, full service restored",
            ),
        ],
        lessons_learned=[
            "DDoS mitigation must handle terabit-scale attacks",
            "Memcached servers should never be exposed to the internet",
            "Having a DDoS scrubbing provider is essential",
            "Quick traffic rerouting capabilities are critical",
        ],
        post_mortem_url="https://github.blog/2018-03-01-ddos-incident-report/",
        tags=["ddos", "security", "memcached", "amplification"],
    ),

    # -----------------------------------------------------------------------
    # 8. Fastly Global CDN Outage (Jun 2021)
    # -----------------------------------------------------------------------
    HistoricalIncident(
        id="fastly-2021-06",
        name="Fastly Global CDN Outage (Jun 2021)",
        provider="generic",
        date=datetime(2021, 6, 8),
        duration=timedelta(minutes=49),
        root_cause=(
            "A software deployment triggered a bug in Fastly's configuration. "
            "A valid customer configuration change triggered the bug, which "
            "caused 85% of Fastly's network to return 503 errors. Major "
            "websites including NYT, Reddit, Twitch, and gov.uk were affected."
        ),
        affected_services=["cdn", "dns"],
        affected_regions=["global"],
        severity="critical",
        timeline=[
            IncidentEvent(
                timestamp_offset=timedelta(minutes=0),
                event_type="full_outage",
                affected_services=["cdn"],
                description="85% of Fastly PoPs begin returning 503 errors",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(minutes=25),
                event_type="partial_recovery",
                affected_services=["cdn"],
                description="Root cause identified, configuration being rolled back",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(minutes=49),
                event_type="full_recovery",
                affected_services=["cdn", "dns"],
                description="All PoPs recovered, full service restored",
            ),
        ],
        lessons_learned=[
            "CDN is a critical single point of failure for many organizations",
            "Multi-CDN strategy protects against provider outages",
            "Software bugs can be triggered by valid customer configurations",
            "Fast detection and rollback capabilities are essential",
        ],
        post_mortem_url="https://www.fastly.com/blog/summary-of-june-8-outage",
        tags=["cdn", "software-bug", "global", "configuration"],
    ),

    # -----------------------------------------------------------------------
    # 9. CrowdStrike BSOD Global Outage (Jul 2024)
    # -----------------------------------------------------------------------
    HistoricalIncident(
        id="crowdstrike-2024-07",
        name="CrowdStrike BSOD Global Outage (Jul 2024)",
        provider="generic",
        date=datetime(2024, 7, 19),
        duration=timedelta(hours=24),
        root_cause=(
            "A faulty sensor configuration update (Channel File 291) in "
            "CrowdStrike's Falcon agent caused Windows systems to crash with "
            "BSOD (Blue Screen of Death). The update was pushed globally to "
            "all Windows hosts running CrowdStrike Falcon. Recovery required "
            "manual intervention (Safe Mode boot and file deletion) on each "
            "affected machine."
        ),
        affected_services=["ec2", "azure_vm", "compute_engine", "server"],
        affected_regions=["global"],
        severity="critical",
        timeline=[
            IncidentEvent(
                timestamp_offset=timedelta(minutes=0),
                event_type="full_outage",
                affected_services=["ec2", "azure_vm", "compute_engine", "server"],
                description="Windows servers worldwide begin BSOD crash loops",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=1, minutes=18),
                event_type="service_degradation",
                affected_services=["ec2", "azure_vm", "compute_engine", "server"],
                description="CrowdStrike identifies and reverts the faulty update",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=6),
                event_type="partial_recovery",
                affected_services=["ec2", "azure_vm"],
                description="Cloud VMs recovering via automated remediation scripts",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=24),
                event_type="full_recovery",
                affected_services=["ec2", "azure_vm", "compute_engine", "server"],
                description="Most systems recovered, some physical servers still being fixed",
            ),
        ],
        lessons_learned=[
            "Endpoint security agents have kernel-level access and can cause OS crashes",
            "Staged rollout of security updates is essential",
            "Recovery should not require manual per-host intervention",
            "Linux/container workloads were unaffected - OS diversity helps",
            "Auto-remediation capabilities for cloud VMs reduce MTTR",
        ],
        post_mortem_url="https://www.crowdstrike.com/falcon-content-update-remediation-and-guidance-hub/",
        tags=["endpoint-security", "windows", "bsod", "global", "manual-recovery"],
    ),

    # -----------------------------------------------------------------------
    # 10. AWS us-east-1 DynamoDB Outage (Sep 2015)
    # -----------------------------------------------------------------------
    HistoricalIncident(
        id="aws-dynamodb-2015-09",
        name="AWS DynamoDB us-east-1 Outage (Sep 2015)",
        provider="aws",
        date=datetime(2015, 9, 20),
        duration=timedelta(hours=5),
        root_cause=(
            "A DynamoDB storage metadata partition became overloaded, causing "
            "latency and errors for DynamoDB tables. The issue cascaded to "
            "other AWS services that depend on DynamoDB for metadata storage."
        ),
        affected_services=["dynamodb", "ec2", "ecs"],
        affected_regions=["us-east-1"],
        severity="major",
        timeline=[
            IncidentEvent(
                timestamp_offset=timedelta(minutes=0),
                event_type="service_degradation",
                affected_services=["dynamodb"],
                description="DynamoDB latency increasing in us-east-1",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(minutes=30),
                event_type="full_outage",
                affected_services=["dynamodb"],
                description="DynamoDB tables returning errors, cascading to dependent services",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=3),
                event_type="partial_recovery",
                affected_services=["dynamodb"],
                description="Metadata partition rebalancing underway",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=5),
                event_type="full_recovery",
                affected_services=["dynamodb", "ec2", "ecs"],
                description="Full service recovery",
            ),
        ],
        lessons_learned=[
            "Metadata services are hidden dependencies for many systems",
            "DynamoDB's internal sharding can become a bottleneck",
            "Use DynamoDB Global Tables for cross-region resilience",
        ],
        post_mortem_url="https://aws.amazon.com/message/5467D2/",
        tags=["database", "metadata", "us-east-1", "cascading"],
    ),

    # -----------------------------------------------------------------------
    # 11. Google Cloud Load Balancer Outage (Nov 2021)
    # -----------------------------------------------------------------------
    HistoricalIncident(
        id="gcp-lb-2021-11",
        name="Google Cloud Load Balancer Outage (Nov 2021)",
        provider="gcp",
        date=datetime(2021, 11, 16),
        duration=timedelta(hours=2, minutes=30),
        root_cause=(
            "A misconfiguration during planned maintenance of Google's global "
            "load balancing infrastructure caused traffic routing errors. "
            "External HTTP(S) Load Balancers returned 502/503 errors."
        ),
        affected_services=["load_balancer", "cdn"],
        affected_regions=["global"],
        severity="major",
        timeline=[
            IncidentEvent(
                timestamp_offset=timedelta(minutes=0),
                event_type="service_degradation",
                affected_services=["load_balancer"],
                description="External LB returning elevated 502/503 error rates",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(minutes=15),
                event_type="full_outage",
                affected_services=["load_balancer", "cdn"],
                description="Global HTTP(S) LB fully impacted",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=1, minutes=30),
                event_type="partial_recovery",
                affected_services=["load_balancer"],
                description="Maintenance rollback initiated",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=2, minutes=30),
                event_type="full_recovery",
                affected_services=["load_balancer", "cdn"],
                description="Full recovery, all error rates normalized",
            ),
        ],
        lessons_learned=[
            "Global load balancers are a critical chokepoint",
            "Maintenance windows need better canary validation",
            "Regional failover for load balancing reduces blast radius",
        ],
        post_mortem_url="https://status.cloud.google.com/incidents/6PM5mNd43NbMqjCZ5REh",
        tags=["load-balancer", "maintenance", "global", "routing"],
    ),

    # -----------------------------------------------------------------------
    # 12. Dyn DNS DDoS Attack (Oct 2016)
    # -----------------------------------------------------------------------
    HistoricalIncident(
        id="dyn-ddos-2016-10",
        name="Dyn DNS DDoS Attack (Oct 2016)",
        provider="generic",
        date=datetime(2016, 10, 21),
        duration=timedelta(hours=8),
        root_cause=(
            "Massive DDoS attack against Dyn's managed DNS infrastructure "
            "using the Mirai botnet (IoT devices). The attack overwhelmed "
            "DNS servers, causing resolution failures for major websites "
            "including Twitter, Netflix, Reddit, Spotify, and GitHub."
        ),
        affected_services=["dns"],
        affected_regions=["us-east-1", "us-west-2"],
        severity="critical",
        timeline=[
            IncidentEvent(
                timestamp_offset=timedelta(minutes=0),
                event_type="full_outage",
                affected_services=["dns"],
                description="First DDoS wave hits Dyn DNS, US East Coast affected",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=2),
                event_type="partial_recovery",
                affected_services=["dns"],
                description="First wave mitigated, services recovering",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=3),
                event_type="full_outage",
                affected_services=["dns"],
                description="Second DDoS wave, broader geographic impact",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=6),
                event_type="partial_recovery",
                affected_services=["dns"],
                description="Second wave mitigated with provider assistance",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=8),
                event_type="full_recovery",
                affected_services=["dns"],
                description="Full DNS service restoration",
            ),
        ],
        lessons_learned=[
            "DNS is a critical SPOF - use multiple DNS providers",
            "IoT botnet attacks can generate massive traffic volumes",
            "Anycast DNS with geographic distribution improves resilience",
            "Low TTL DNS records speed up failover to backup providers",
        ],
        post_mortem_url="https://dyn.com/blog/dyn-analysis-summary-of-friday-october-21-attack/",
        tags=["ddos", "dns", "mirai", "iot-botnet"],
    ),

    # -----------------------------------------------------------------------
    # 13. AWS Kinesis us-east-1 Outage (Nov 2020)
    # -----------------------------------------------------------------------
    HistoricalIncident(
        id="aws-kinesis-2020-11",
        name="AWS Kinesis us-east-1 Outage (Nov 2020)",
        provider="aws",
        date=datetime(2020, 11, 25),
        duration=timedelta(hours=10),
        root_cause=(
            "Addition of capacity to Kinesis front-end fleet triggered a bug "
            "that caused excessive thread consumption. The cascading impact "
            "affected CloudWatch, Lambda, and other services that depend on "
            "Kinesis for internal data streaming."
        ),
        affected_services=["lambda", "cloudwatch", "ec2", "ecs"],
        affected_regions=["us-east-1"],
        severity="critical",
        timeline=[
            IncidentEvent(
                timestamp_offset=timedelta(minutes=0),
                event_type="service_degradation",
                affected_services=["lambda"],
                description="Kinesis front-end capacity addition triggers thread exhaustion",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(minutes=30),
                event_type="full_outage",
                affected_services=["lambda", "cloudwatch"],
                description="CloudWatch and Lambda significantly impaired",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=5),
                event_type="partial_recovery",
                affected_services=["lambda"],
                description="Kinesis front-end fleet scaling underway",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=10),
                event_type="full_recovery",
                affected_services=["lambda", "cloudwatch", "ec2", "ecs"],
                description="All services fully recovered",
            ),
        ],
        lessons_learned=[
            "Capacity additions can trigger unexpected failure modes",
            "Thread exhaustion is a common cascading failure pattern",
            "Internal service dependencies create hidden failure paths",
            "CloudWatch outage means you lose visibility during the incident",
        ],
        post_mortem_url="https://aws.amazon.com/message/11201/",
        tags=["capacity", "thread-exhaustion", "cascading", "us-east-1"],
    ),

    # -----------------------------------------------------------------------
    # 14. Slack Major Outage (Feb 2022)
    # -----------------------------------------------------------------------
    HistoricalIncident(
        id="slack-2022-02",
        name="Slack Major Outage (Feb 2022)",
        provider="generic",
        date=datetime(2022, 2, 22),
        duration=timedelta(hours=5),
        root_cause=(
            "A database infrastructure change caused unexpected load on "
            "Slack's data tier. The resulting database performance issues "
            "cascaded to application servers and message delivery services."
        ),
        affected_services=["database", "server", "cache", "queue"],
        affected_regions=["global"],
        severity="major",
        timeline=[
            IncidentEvent(
                timestamp_offset=timedelta(minutes=0),
                event_type="service_degradation",
                affected_services=["database"],
                description="Database latency increasing after infrastructure change",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(minutes=30),
                event_type="full_outage",
                affected_services=["database", "server"],
                description="Message delivery failing, workspace loading issues",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=3),
                event_type="partial_recovery",
                affected_services=["server"],
                description="Database change rolled back, recovery in progress",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=5),
                event_type="full_recovery",
                affected_services=["database", "server", "cache", "queue"],
                description="Full service restoration",
            ),
        ],
        lessons_learned=[
            "Database changes should be performed with staged rollout",
            "Database performance issues cascade rapidly to application tier",
            "Connection pooling and circuit breakers limit cascade impact",
        ],
        post_mortem_url="https://status.slack.com",
        tags=["database", "cascading", "performance"],
    ),

    # -----------------------------------------------------------------------
    # 15. AWS us-east-1 EBS & RDS Outage (Apr 2011)
    # -----------------------------------------------------------------------
    HistoricalIncident(
        id="aws-ebs-2011-04",
        name="AWS EBS/RDS us-east-1 Outage (Apr 2011)",
        provider="aws",
        date=datetime(2011, 4, 21),
        duration=timedelta(hours=48),
        root_cause=(
            "A network configuration change during maintenance caused an EBS "
            "re-mirroring storm. The massive volume of re-mirroring requests "
            "overwhelmed the EBS control plane and caused widespread EBS "
            "volume unavailability in us-east-1."
        ),
        affected_services=["ec2", "rds", "s3"],
        affected_regions=["us-east-1"],
        severity="critical",
        timeline=[
            IncidentEvent(
                timestamp_offset=timedelta(minutes=0),
                event_type="service_degradation",
                affected_services=["ec2"],
                description="EBS volumes begin experiencing I/O errors",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=1),
                event_type="full_outage",
                affected_services=["ec2", "rds"],
                description="Widespread EBS volume failures, RDS instances impacted",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=24),
                event_type="partial_recovery",
                affected_services=["ec2"],
                description="EBS re-mirroring backlog clearing, volumes recovering",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=48),
                event_type="full_recovery",
                affected_services=["ec2", "rds", "s3"],
                description="Full recovery, but some data loss for stuck EBS volumes",
            ),
        ],
        lessons_learned=[
            "Multi-AZ deployments protect against single-AZ EBS failures",
            "EBS volume recovery can take days in extreme cases",
            "This incident was the catalyst for the modern 'AZ' deployment model",
            "Regular backups and cross-region replication are essential",
        ],
        post_mortem_url="https://aws.amazon.com/message/65648/",
        tags=["ebs", "storage", "re-mirroring", "us-east-1", "data-loss"],
    ),

    # -----------------------------------------------------------------------
    # 16. Roblox 73-hour Outage (Oct 2021)
    # -----------------------------------------------------------------------
    HistoricalIncident(
        id="roblox-2021-10",
        name="Roblox 73-Hour Outage (Oct 2021)",
        provider="generic",
        date=datetime(2021, 10, 28),
        duration=timedelta(hours=73),
        root_cause=(
            "A subtle internal service issue related to HashiCorp Consul "
            "caused Consul cluster instability under high contention. "
            "The cascading effect took down backend services, game servers, "
            "and data stores. Recovery was extremely complex due to the "
            "distributed nature of the failure."
        ),
        affected_services=["server", "database", "cache", "queue"],
        affected_regions=["global"],
        severity="critical",
        timeline=[
            IncidentEvent(
                timestamp_offset=timedelta(minutes=0),
                event_type="service_degradation",
                affected_services=["server"],
                description="Consul cluster instability detected",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=2),
                event_type="full_outage",
                affected_services=["server", "database", "cache"],
                description="Cascading failures bring down all backend services",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=48),
                event_type="partial_recovery",
                affected_services=["server"],
                description="Root cause identified as Consul contention, remediation underway",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=73),
                event_type="full_recovery",
                affected_services=["server", "database", "cache", "queue"],
                description="Full platform restoration after extensive debugging",
            ),
        ],
        lessons_learned=[
            "Service discovery systems are critical infrastructure",
            "Distributed system failures can be extremely hard to diagnose",
            "Game-day exercises should include service discovery failure scenarios",
            "Observability tools must not depend on the same infrastructure they monitor",
        ],
        post_mortem_url="https://blog.roblox.com/2022/01/roblox-return-to-service-10-28-10-31-2021/",
        tags=["service-discovery", "consul", "cascading", "prolonged-outage"],
    ),

    # -----------------------------------------------------------------------
    # 17. Azure Active Directory Outage (Mar 2021)
    # -----------------------------------------------------------------------
    HistoricalIncident(
        id="azure-ad-2021-03",
        name="Azure Active Directory Global Outage (Mar 2021)",
        provider="azure",
        date=datetime(2021, 3, 15),
        duration=timedelta(hours=14),
        root_cause=(
            "A rotation of signing keys used to validate tokens for Azure AD "
            "authentication went wrong. A metadata publishing issue meant some "
            "key information was not properly distributed, causing authentication "
            "failures across Azure and Microsoft 365 services worldwide."
        ),
        affected_services=["azure_vm", "azure_sql", "azure_storage", "server"],
        affected_regions=["global"],
        severity="critical",
        timeline=[
            IncidentEvent(
                timestamp_offset=timedelta(minutes=0),
                event_type="service_degradation",
                affected_services=["azure_vm"],
                description="Authentication failures detected for Azure AD tokens",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(minutes=30),
                event_type="full_outage",
                affected_services=["azure_vm", "azure_sql", "azure_storage", "server"],
                description="Widespread auth failures impact all Azure and M365 services",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=8),
                event_type="partial_recovery",
                affected_services=["azure_vm"],
                description="Key rotation fix being propagated globally",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=14),
                event_type="full_recovery",
                affected_services=["azure_vm", "azure_sql", "azure_storage", "server"],
                description="All regions recovered, authentication normalized",
            ),
        ],
        lessons_learned=[
            "Authentication/identity services are the most critical dependency",
            "Key rotation procedures must be tested in staging environments",
            "Cached credentials can provide temporary resilience during auth outages",
            "Multi-identity-provider strategy reduces blast radius",
        ],
        post_mortem_url="https://msrc-blog.microsoft.com/2021/03/",
        tags=["authentication", "identity", "key-rotation", "global"],
    ),

    # -----------------------------------------------------------------------
    # 18. OVHcloud Fire (Mar 2021)
    # -----------------------------------------------------------------------
    HistoricalIncident(
        id="ovh-fire-2021-03",
        name="OVHcloud Strasbourg Data Center Fire (Mar 2021)",
        provider="generic",
        date=datetime(2021, 3, 10),
        duration=timedelta(hours=720),  # Weeks for full recovery
        root_cause=(
            "A fire broke out at OVHcloud's SBG2 data center in Strasbourg, "
            "France, completely destroying it and partially damaging SBG1. "
            "3.6 million websites were affected. Customers without offsite "
            "backups suffered permanent data loss."
        ),
        affected_services=["server", "database", "s3"],
        affected_regions=["eu-west"],
        severity="critical",
        timeline=[
            IncidentEvent(
                timestamp_offset=timedelta(minutes=0),
                event_type="full_outage",
                affected_services=["server", "database", "s3"],
                description="Fire destroys SBG2 data center, SBG1 partially damaged",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=24),
                event_type="service_degradation",
                affected_services=["server"],
                description="Remaining data centers handling overflow, some services back",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=168),
                event_type="partial_recovery",
                affected_services=["server", "database"],
                description="SBG1/SBG3/SBG4 services being restored from backups",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=720),
                event_type="full_recovery",
                affected_services=["server", "database", "s3"],
                description="New data center operational, customers migrated",
            ),
        ],
        lessons_learned=[
            "Physical disasters can permanently destroy data",
            "Offsite and cross-region backups are absolutely critical",
            "Data center fire suppression systems must be regularly tested",
            "Business continuity plans must account for total facility loss",
        ],
        post_mortem_url="https://www.ovhcloud.com/en/lp/sbg-restart/",
        tags=["physical-disaster", "fire", "data-loss", "eu-west"],
    ),
]
