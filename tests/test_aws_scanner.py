"""Tests for AWS auto-discovery scanner.

All boto3 calls are mocked — tests work without actual AWS credentials.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from faultray.model.components import ComponentType, Dependency
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scanner(region: str = "ap-northeast-1", profile: str | None = None):
    """Import and instantiate AWSScanner (ensures module is importable)."""
    from faultray.discovery.aws_scanner import AWSScanner
    return AWSScanner(region=region, profile=profile)


def _mock_boto3_session(**service_mocks):
    """Create a mock boto3 session that returns pre-configured service clients.

    ``service_mocks`` maps service names (e.g. ``ec2``, ``rds``) to
    already-configured MagicMock client objects.
    """
    session = MagicMock()

    def _client(service_name, **kwargs):
        if service_name in service_mocks:
            return service_mocks[service_name]
        # Return an empty mock for services without explicit mocks
        empty = MagicMock()
        # Set up paginators that return empty results
        paginator = MagicMock()
        paginator.paginate.return_value = iter([])
        empty.get_paginator.return_value = paginator
        empty.list_buckets.return_value = {"Buckets": []}
        empty.list_queues.return_value = {"QueueUrls": []}
        empty.list_hosted_zones.return_value = {"HostedZones": []}
        empty.list_web_acls.return_value = {"WebACLs": []}
        empty.describe_flow_logs.return_value = {"FlowLogs": []}
        return empty

    session.client.side_effect = _client
    return session


def _ec2_client_with_instances(instances, security_groups=None):
    """Build a mock EC2 client that returns the given instances."""
    ec2 = MagicMock()

    # describe_instances paginator
    inst_paginator = MagicMock()
    inst_paginator.paginate.return_value = iter([
        {"Reservations": [{"Instances": instances}]}
    ])

    # describe_security_groups paginator
    sg_paginator = MagicMock()
    sg_paginator.paginate.return_value = iter([
        {"SecurityGroups": security_groups or []}
    ])

    # describe_route_tables paginator
    rt_paginator = MagicMock()
    rt_paginator.paginate.return_value = iter([{"RouteTables": []}])

    # describe_subnets paginator
    sub_paginator = MagicMock()
    sub_paginator.paginate.return_value = iter([{"Subnets": []}])

    def _get_paginator(op):
        return {
            "describe_instances": inst_paginator,
            "describe_security_groups": sg_paginator,
            "describe_route_tables": rt_paginator,
            "describe_subnets": sub_paginator,
        }.get(op, MagicMock())

    ec2.get_paginator.side_effect = _get_paginator
    ec2.describe_flow_logs.return_value = {"FlowLogs": []}
    return ec2


def _rds_client_with_clusters(clusters=None, instances=None):
    """Build a mock RDS client."""
    rds = MagicMock()

    cluster_paginator = MagicMock()
    cluster_paginator.paginate.return_value = iter([
        {"DBClusters": clusters or []}
    ])

    instance_paginator = MagicMock()
    instance_paginator.paginate.return_value = iter([
        {"DBInstances": instances or []}
    ])

    def _get_paginator(op):
        if op == "describe_db_clusters":
            return cluster_paginator
        if op == "describe_db_instances":
            return instance_paginator
        return MagicMock()

    rds.get_paginator.side_effect = _get_paginator
    return rds


def _elbv2_client_with_lbs(load_balancers):
    """Build a mock ELBv2 client."""
    elbv2 = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = iter([
        {"LoadBalancers": load_balancers}
    ])
    elbv2.get_paginator.return_value = paginator
    elbv2.describe_target_groups.return_value = {"TargetGroups": []}
    return elbv2


def _s3_client_with_buckets(buckets, region="ap-northeast-1"):
    """Build a mock S3 client."""
    s3 = MagicMock()
    s3.list_buckets.return_value = {
        "Buckets": [{"Name": b} for b in buckets]
    }
    s3.get_bucket_location.return_value = {"LocationConstraint": region}
    s3.get_bucket_encryption.return_value = {
        "ServerSideEncryptionConfiguration": {
            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
        }
    }
    s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
    return s3


def _lambda_client_with_functions(functions):
    """Build a mock Lambda client."""
    lam = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = iter([{"Functions": functions}])
    lam.get_paginator.return_value = paginator
    return lam


def _sqs_client_with_queues(queue_urls):
    """Build a mock SQS client."""
    sqs = MagicMock()
    sqs.list_queues.return_value = {"QueueUrls": queue_urls}
    sqs.get_queue_attributes.return_value = {
        "Attributes": {
            "ApproximateNumberOfMessages": "42",
            "KmsMasterKeyId": "arn:aws:kms:ap-northeast-1:123456:key/abc",
        }
    }
    return sqs


def _cloudfront_client_with_dists(distributions):
    """Build a mock CloudFront client."""
    cf = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = iter([
        {"DistributionList": {"Items": distributions}}
    ])
    cf.get_paginator.return_value = paginator
    return cf


# ---------------------------------------------------------------------------
# Test: EC2 discovery
# ---------------------------------------------------------------------------

class TestEC2Discovery:
    @patch("faultray.discovery.aws_scanner._boto3_session")
    def test_discover_running_ec2_instances(self, mock_session_fn):
        instances = [
            {
                "InstanceId": "i-abc123",
                "State": {"Name": "running"},
                "InstanceType": "t3.medium",
                "PrivateIpAddress": "10.0.1.5",
                "Placement": {"AvailabilityZone": "ap-northeast-1a"},
                "SubnetId": "subnet-aaa",
                "SecurityGroups": [{"GroupId": "sg-111"}],
                "Tags": [{"Key": "Name", "Value": "web-server-1"}],
            },
            {
                "InstanceId": "i-stopped",
                "State": {"Name": "stopped"},
                "InstanceType": "t3.small",
                "PrivateIpAddress": "10.0.1.6",
                "Placement": {"AvailabilityZone": "ap-northeast-1b"},
                "SubnetId": "subnet-bbb",
                "SecurityGroups": [],
                "Tags": [],
            },
        ]

        ec2 = _ec2_client_with_instances(instances)
        session = _mock_boto3_session(ec2=ec2)
        mock_session_fn.return_value = session

        scanner = _make_scanner()
        result = scanner.scan()

        # Only running instances should be discovered
        ec2_comps = [c for c in result.graph.components.values() if c.id.startswith("ec2-")]
        assert len(ec2_comps) == 1
        assert ec2_comps[0].name == "web-server-1"
        assert ec2_comps[0].type == ComponentType.APP_SERVER
        assert ec2_comps[0].host == "10.0.1.5"
        assert "instance_type:t3.medium" in ec2_comps[0].tags

    @patch("faultray.discovery.aws_scanner._boto3_session")
    def test_ec2_without_name_tag(self, mock_session_fn):
        instances = [
            {
                "InstanceId": "i-noname",
                "State": {"Name": "running"},
                "InstanceType": "m5.large",
                "PrivateIpAddress": "10.0.2.1",
                "Placement": {"AvailabilityZone": "ap-northeast-1c"},
                "SubnetId": "subnet-ccc",
                "SecurityGroups": [],
                "Tags": [],
            },
        ]
        ec2 = _ec2_client_with_instances(instances)
        session = _mock_boto3_session(ec2=ec2)
        mock_session_fn.return_value = session

        scanner = _make_scanner()
        result = scanner.scan()

        comp = result.graph.get_component("ec2-i-noname")
        assert comp is not None
        assert comp.name == "i-noname"  # Falls back to instance id


# ---------------------------------------------------------------------------
# Test: RDS discovery
# ---------------------------------------------------------------------------

class TestRDSDiscovery:
    @patch("faultray.discovery.aws_scanner._boto3_session")
    def test_discover_aurora_cluster(self, mock_session_fn):
        clusters = [
            {
                "DBClusterIdentifier": "prod-aurora",
                "Endpoint": "prod-aurora.cluster-xyz.ap-northeast-1.rds.amazonaws.com",
                "Port": 3306,
                "Engine": "aurora-mysql",
                "StorageEncrypted": True,
                "BackupRetentionPeriod": 7,
                "AvailabilityZones": ["ap-northeast-1a", "ap-northeast-1c"],
                "DBClusterMembers": [
                    {"DBInstanceIdentifier": "prod-aurora-1"},
                    {"DBInstanceIdentifier": "prod-aurora-2"},
                ],
                "VpcSecurityGroups": [{"VpcSecurityGroupId": "sg-rds-1"}],
            }
        ]

        ec2 = _ec2_client_with_instances([])
        rds = _rds_client_with_clusters(clusters=clusters, instances=[])
        session = _mock_boto3_session(ec2=ec2, rds=rds)
        mock_session_fn.return_value = session

        scanner = _make_scanner()
        result = scanner.scan()

        comp = result.graph.get_component("rds-prod-aurora")
        assert comp is not None
        assert comp.type == ComponentType.DATABASE
        assert comp.replicas == 2  # 2 cluster members
        assert comp.security.encryption_at_rest is True
        assert comp.security.backup_enabled is True
        assert comp.failover.enabled is True  # multi-AZ
        assert "aurora" in comp.tags

    @patch("faultray.discovery.aws_scanner._boto3_session")
    def test_discover_standalone_rds(self, mock_session_fn):
        instances = [
            {
                "DBInstanceIdentifier": "staging-pg",
                "DBClusterIdentifier": None,
                "Engine": "postgres",
                "MultiAZ": False,
                "StorageEncrypted": False,
                "BackupRetentionPeriod": 0,
                "Endpoint": {"Address": "staging-pg.xyz.ap-northeast-1.rds.amazonaws.com", "Port": 5432},
                "AvailabilityZone": "ap-northeast-1a",
                "VpcSecurityGroups": [],
            }
        ]

        ec2 = _ec2_client_with_instances([])
        rds = _rds_client_with_clusters(clusters=[], instances=instances)
        session = _mock_boto3_session(ec2=ec2, rds=rds)
        mock_session_fn.return_value = session

        scanner = _make_scanner()
        result = scanner.scan()

        comp = result.graph.get_component("rds-staging-pg")
        assert comp is not None
        assert comp.type == ComponentType.DATABASE
        assert comp.replicas == 1  # single-AZ
        assert comp.security.encryption_at_rest is False
        assert comp.security.backup_enabled is False
        assert comp.failover.enabled is False


# ---------------------------------------------------------------------------
# Test: ALB discovery
# ---------------------------------------------------------------------------

class TestALBDiscovery:
    @patch("faultray.discovery.aws_scanner._boto3_session")
    def test_discover_alb(self, mock_session_fn):
        load_balancers = [
            {
                "LoadBalancerName": "prod-alb",
                "LoadBalancerArn": "arn:aws:elasticloadbalancing:ap-northeast-1:123456:loadbalancer/app/prod-alb/abc",
                "Type": "application",
                "DNSName": "prod-alb-123.ap-northeast-1.elb.amazonaws.com",
                "AvailabilityZones": [
                    {"ZoneName": "ap-northeast-1a"},
                    {"ZoneName": "ap-northeast-1c"},
                ],
                "SecurityGroups": ["sg-alb-1"],
            }
        ]

        ec2 = _ec2_client_with_instances([])
        elbv2 = _elbv2_client_with_lbs(load_balancers)
        session = _mock_boto3_session(ec2=ec2, elbv2=elbv2)
        mock_session_fn.return_value = session

        scanner = _make_scanner()
        result = scanner.scan()

        comp = result.graph.get_component("alb-prod-alb")
        assert comp is not None
        assert comp.type == ComponentType.LOAD_BALANCER
        assert comp.replicas == 2  # 2 AZs
        assert comp.failover.enabled is True  # multi-AZ


# ---------------------------------------------------------------------------
# Test: S3 discovery
# ---------------------------------------------------------------------------

class TestS3Discovery:
    @patch("faultray.discovery.aws_scanner._boto3_session")
    def test_discover_s3_buckets(self, mock_session_fn):
        ec2 = _ec2_client_with_instances([])
        s3 = _s3_client_with_buckets(["my-data-bucket", "my-logs-bucket"])
        session = _mock_boto3_session(ec2=ec2, s3=s3)
        mock_session_fn.return_value = session

        scanner = _make_scanner()
        result = scanner.scan()

        comp1 = result.graph.get_component("s3-my-data-bucket")
        assert comp1 is not None
        assert comp1.type == ComponentType.STORAGE
        assert comp1.replicas == 3  # S3 inherent replication
        assert comp1.security.encryption_at_rest is True
        assert comp1.security.backup_enabled is True  # versioning enabled

        comp2 = result.graph.get_component("s3-my-logs-bucket")
        assert comp2 is not None


# ---------------------------------------------------------------------------
# Test: SQS discovery
# ---------------------------------------------------------------------------

class TestSQSDiscovery:
    @patch("faultray.discovery.aws_scanner._boto3_session")
    def test_discover_sqs_queues(self, mock_session_fn):
        ec2 = _ec2_client_with_instances([])
        sqs = _sqs_client_with_queues([
            "https://sqs.ap-northeast-1.amazonaws.com/123456/order-queue",
        ])
        session = _mock_boto3_session(ec2=ec2, sqs=sqs)
        mock_session_fn.return_value = session

        scanner = _make_scanner()
        result = scanner.scan()

        comp = result.graph.get_component("sqs-order-queue")
        assert comp is not None
        assert comp.type == ComponentType.QUEUE
        assert comp.security.encryption_at_rest is True  # KMS key set
        assert comp.metrics.network_connections == 42


# ---------------------------------------------------------------------------
# Test: Dependency inference from security groups
# ---------------------------------------------------------------------------

class TestDependencyInference:
    @patch("faultray.discovery.aws_scanner._boto3_session")
    def test_sg_based_dependency_inference(self, mock_session_fn):
        """If sg-app allows inbound from sg-web on port 8080 then web->app."""
        instances = [
            {
                "InstanceId": "i-web1",
                "State": {"Name": "running"},
                "InstanceType": "t3.small",
                "PrivateIpAddress": "10.0.1.1",
                "Placement": {"AvailabilityZone": "ap-northeast-1a"},
                "SubnetId": "subnet-a",
                "SecurityGroups": [{"GroupId": "sg-web"}],
                "Tags": [{"Key": "Name", "Value": "web"}],
            },
            {
                "InstanceId": "i-app1",
                "State": {"Name": "running"},
                "InstanceType": "t3.medium",
                "PrivateIpAddress": "10.0.2.1",
                "Placement": {"AvailabilityZone": "ap-northeast-1a"},
                "SubnetId": "subnet-b",
                "SecurityGroups": [{"GroupId": "sg-app"}],
                "Tags": [{"Key": "Name", "Value": "app"}],
            },
        ]

        security_groups = [
            {
                "GroupId": "sg-app",
                "IpPermissions": [
                    {
                        "FromPort": 8080,
                        "ToPort": 8080,
                        "UserIdGroupPairs": [{"GroupId": "sg-web"}],
                    }
                ],
            },
            {
                "GroupId": "sg-web",
                "IpPermissions": [],
            },
        ]

        ec2 = _ec2_client_with_instances(instances, security_groups=security_groups)
        session = _mock_boto3_session(ec2=ec2)
        mock_session_fn.return_value = session

        scanner = _make_scanner()
        result = scanner.scan()

        # web should depend on app (web sends traffic to app)
        edges = result.graph.all_dependency_edges()
        assert len(edges) >= 1

        # Find the edge: sg-web component -> sg-app component
        dep = None
        for e in edges:
            if "i-web1" in e.source_id and "i-app1" in e.target_id:
                dep = e
                break
        assert dep is not None, f"Expected dependency from web to app. Got edges: {[(e.source_id, e.target_id) for e in edges]}"
        assert dep.dependency_type == "optional"  # port 8080 is not in _DB_CACHE_PORTS

    @patch("faultray.discovery.aws_scanner._boto3_session")
    def test_sg_db_port_creates_requires_dependency(self, mock_session_fn):
        """If sg-db allows inbound from sg-app on port 5432 then dep_type='requires'."""
        instances = [
            {
                "InstanceId": "i-app",
                "State": {"Name": "running"},
                "InstanceType": "t3.small",
                "PrivateIpAddress": "10.0.1.1",
                "Placement": {"AvailabilityZone": "ap-northeast-1a"},
                "SubnetId": "subnet-a",
                "SecurityGroups": [{"GroupId": "sg-app"}],
                "Tags": [{"Key": "Name", "Value": "app-server"}],
            },
        ]

        security_groups = [
            {
                "GroupId": "sg-db",
                "IpPermissions": [
                    {
                        "FromPort": 5432,
                        "ToPort": 5432,
                        "UserIdGroupPairs": [{"GroupId": "sg-app"}],
                    }
                ],
            },
        ]

        # Create an RDS instance with sg-db
        rds_instances = [
            {
                "DBInstanceIdentifier": "mydb",
                "DBClusterIdentifier": None,
                "Engine": "postgres",
                "MultiAZ": False,
                "StorageEncrypted": False,
                "BackupRetentionPeriod": 1,
                "Endpoint": {"Address": "mydb.xyz.rds.amazonaws.com", "Port": 5432},
                "AvailabilityZone": "ap-northeast-1a",
                "VpcSecurityGroups": [{"VpcSecurityGroupId": "sg-db"}],
            }
        ]

        ec2 = _ec2_client_with_instances(instances, security_groups=security_groups)
        rds = _rds_client_with_clusters(clusters=[], instances=rds_instances)
        session = _mock_boto3_session(ec2=ec2, rds=rds)
        mock_session_fn.return_value = session

        scanner = _make_scanner()
        result = scanner.scan()

        edges = result.graph.all_dependency_edges()
        # Find the app -> db dependency
        db_dep = None
        for e in edges:
            if "i-app" in e.source_id and "mydb" in e.target_id:
                db_dep = e
                break
        assert db_dep is not None
        assert db_dep.dependency_type == "requires"  # port 5432 is a DB port


# ---------------------------------------------------------------------------
# Test: Security profile detection
# ---------------------------------------------------------------------------

class TestSecurityDetection:
    @patch("faultray.discovery.aws_scanner._boto3_session")
    def test_encrypted_vs_unencrypted(self, mock_session_fn):
        """RDS with StorageEncrypted=True vs False."""
        clusters = [
            {
                "DBClusterIdentifier": "encrypted-db",
                "Endpoint": "enc.rds.amazonaws.com",
                "Port": 3306,
                "Engine": "aurora-mysql",
                "StorageEncrypted": True,
                "BackupRetentionPeriod": 7,
                "AvailabilityZones": ["ap-northeast-1a"],
                "DBClusterMembers": [{"DBInstanceIdentifier": "enc-1"}],
                "VpcSecurityGroups": [],
            },
        ]
        unencrypted_instances = [
            {
                "DBInstanceIdentifier": "unencrypted-db",
                "DBClusterIdentifier": None,
                "Engine": "postgres",
                "MultiAZ": False,
                "StorageEncrypted": False,
                "BackupRetentionPeriod": 0,
                "Endpoint": {"Address": "unenc.rds.amazonaws.com", "Port": 5432},
                "AvailabilityZone": "ap-northeast-1a",
                "VpcSecurityGroups": [],
            }
        ]

        ec2 = _ec2_client_with_instances([])
        rds = _rds_client_with_clusters(clusters=clusters, instances=unencrypted_instances)
        session = _mock_boto3_session(ec2=ec2, rds=rds)
        mock_session_fn.return_value = session

        scanner = _make_scanner()
        result = scanner.scan()

        enc_comp = result.graph.get_component("rds-encrypted-db")
        assert enc_comp is not None
        assert enc_comp.security.encryption_at_rest is True

        unenc_comp = result.graph.get_component("rds-unencrypted-db")
        assert unenc_comp is not None
        assert unenc_comp.security.encryption_at_rest is False

    @patch("faultray.discovery.aws_scanner._boto3_session")
    def test_port_443_sets_encryption_in_transit(self, mock_session_fn):
        load_balancers = [
            {
                "LoadBalancerName": "https-alb",
                "LoadBalancerArn": "arn:aws:elb:ap-northeast-1:123:lb/app/https-alb/x",
                "Type": "application",
                "DNSName": "https-alb.elb.amazonaws.com",
                "AvailabilityZones": [{"ZoneName": "ap-northeast-1a"}],
                "SecurityGroups": [],
            }
        ]

        ec2 = _ec2_client_with_instances([])
        elbv2 = _elbv2_client_with_lbs(load_balancers)
        session = _mock_boto3_session(ec2=ec2, elbv2=elbv2)
        mock_session_fn.return_value = session

        scanner = _make_scanner()
        result = scanner.scan()

        comp = result.graph.get_component("alb-https-alb")
        assert comp is not None
        assert comp.port == 443
        assert comp.security.encryption_in_transit is True


# ---------------------------------------------------------------------------
# Test: Empty AWS account
# ---------------------------------------------------------------------------

class TestEmptyAccount:
    @patch("faultray.discovery.aws_scanner._boto3_session")
    def test_empty_aws_account(self, mock_session_fn):
        ec2 = _ec2_client_with_instances([])
        session = _mock_boto3_session(ec2=ec2)
        mock_session_fn.return_value = session

        scanner = _make_scanner()
        result = scanner.scan()

        assert result.components_found == 0
        assert result.dependencies_inferred == 0
        assert len(result.graph.components) == 0


# ---------------------------------------------------------------------------
# Test: Permission denied handling
# ---------------------------------------------------------------------------

class TestPermissionDenied:
    @patch("faultray.discovery.aws_scanner._boto3_session")
    def test_permission_denied_graceful(self, mock_session_fn):
        """If EC2 describe_instances raises ClientError, scanner should warn but not crash."""
        ec2 = MagicMock()
        inst_paginator = MagicMock()
        inst_paginator.paginate.side_effect = Exception("AccessDeniedException: not authorized")
        ec2.get_paginator.return_value = inst_paginator

        session = _mock_boto3_session(ec2=ec2)
        mock_session_fn.return_value = session

        scanner = _make_scanner()
        result = scanner.scan()

        assert any("EC2" in w or "AccessDenied" in w for w in result.warnings)
        # Scanner should still complete
        assert isinstance(result.graph, InfraGraph)


# ---------------------------------------------------------------------------
# Test: boto3 not installed handling
# ---------------------------------------------------------------------------

class TestBoto3NotInstalled:
    def test_boto3_import_error(self):
        """If boto3 is not available, _boto3_session should raise RuntimeError."""
        from faultray.discovery.aws_scanner import _boto3_session

        with patch.dict(sys.modules, {"boto3": None}):
            # When boto3 is set to None in sys.modules, import will fail
            with patch("builtins.__import__", side_effect=ImportError("No module named 'boto3'")):
                with pytest.raises(RuntimeError, match="boto3 is required"):
                    _boto3_session("ap-northeast-1")


# ---------------------------------------------------------------------------
# Test: YAML export
# ---------------------------------------------------------------------------

class TestYAMLExport:
    def test_export_yaml_roundtrip(self, tmp_path):
        """Export a graph to YAML and verify it can be loaded back."""
        from faultray.discovery.aws_scanner import export_yaml
        from faultray.model.loader import load_yaml
        from faultray.model.components import Component, SecurityProfile, Capacity

        graph = InfraGraph()
        graph.add_component(Component(
            id="test-alb",
            name="Test ALB",
            type=ComponentType.LOAD_BALANCER,
            host="test-alb.elb.amazonaws.com",
            port=443,
            replicas=2,
            capacity=Capacity(max_connections=50000, max_rps=100000),
            security=SecurityProfile(
                encryption_in_transit=True,
                waf_protected=True,
            ),
            tags=["alb"],
        ))
        graph.add_component(Component(
            id="test-app",
            name="Test App",
            type=ComponentType.APP_SERVER,
            replicas=3,
        ))
        graph.add_dependency(Dependency(
            source_id="test-alb",
            target_id="test-app",
            dependency_type="requires",
            protocol="http",
            port=8080,
        ))

        yaml_path = tmp_path / "export.yaml"
        export_yaml(graph, yaml_path)

        assert yaml_path.exists()

        # Load it back
        loaded_graph = load_yaml(yaml_path)
        assert len(loaded_graph.components) == 2
        assert loaded_graph.get_component("test-alb") is not None
        assert loaded_graph.get_component("test-app") is not None

        alb = loaded_graph.get_component("test-alb")
        assert alb.type == ComponentType.LOAD_BALANCER
        assert alb.replicas == 2
        assert alb.security.encryption_in_transit is True

        edges = loaded_graph.all_dependency_edges()
        assert len(edges) == 1
        assert edges[0].source_id == "test-alb"
        assert edges[0].target_id == "test-app"

    def test_export_yaml_empty_graph(self, tmp_path):
        """Exporting an empty graph produces valid YAML."""
        from faultray.discovery.aws_scanner import export_yaml

        graph = InfraGraph()
        yaml_path = tmp_path / "empty.yaml"
        export_yaml(graph, yaml_path)

        import yaml
        data = yaml.safe_load(yaml_path.read_text())
        assert data["components"] == []


# ---------------------------------------------------------------------------
# Test: Component type mapping
# ---------------------------------------------------------------------------

class TestComponentTypeMapping:
    def test_aws_type_map_completeness(self):
        """Verify AWS_TYPE_MAP covers all expected services."""
        from faultray.discovery.aws_scanner import AWS_TYPE_MAP

        expected_services = {
            "ec2", "rds", "aurora", "elasticache", "alb", "nlb",
            "ecs", "eks", "s3", "sqs", "cloudfront", "route53", "lambda",
        }
        assert set(AWS_TYPE_MAP.keys()) == expected_services

    def test_all_mapped_types_are_valid(self):
        """All values in AWS_TYPE_MAP must be valid ComponentTypes."""
        from faultray.discovery.aws_scanner import AWS_TYPE_MAP

        for service, comp_type in AWS_TYPE_MAP.items():
            assert isinstance(comp_type, ComponentType), f"{service} mapped to non-ComponentType: {comp_type}"


# ---------------------------------------------------------------------------
# Test: Metric enrichment
# ---------------------------------------------------------------------------

class TestMetricEnrichment:
    @patch("faultray.discovery.aws_scanner._boto3_session")
    def test_ec2_cpu_enrichment(self, mock_session_fn):
        """CloudWatch CPU metrics should be applied to EC2 components."""
        instances = [
            {
                "InstanceId": "i-metrics",
                "State": {"Name": "running"},
                "InstanceType": "m5.large",
                "PrivateIpAddress": "10.0.1.1",
                "Placement": {"AvailabilityZone": "ap-northeast-1a"},
                "SubnetId": "subnet-a",
                "SecurityGroups": [],
                "Tags": [{"Key": "Name", "Value": "metrics-test"}],
            },
        ]

        ec2 = _ec2_client_with_instances(instances)

        cw = MagicMock()
        cw.get_metric_statistics.return_value = {
            "Datapoints": [{"Average": 42.5}]
        }

        session = _mock_boto3_session(ec2=ec2, cloudwatch=cw)
        mock_session_fn.return_value = session

        scanner = _make_scanner()
        result = scanner.scan()

        comp = result.graph.get_component("ec2-i-metrics")
        assert comp is not None
        assert comp.metrics.cpu_percent == 42.5


# ---------------------------------------------------------------------------
# Test: Multi-AZ detection
# ---------------------------------------------------------------------------

class TestMultiAZDetection:
    @patch("faultray.discovery.aws_scanner._boto3_session")
    def test_rds_multi_az(self, mock_session_fn):
        """MultiAZ RDS instance should have failover enabled and replicas=2."""
        instances = [
            {
                "DBInstanceIdentifier": "multi-az-db",
                "DBClusterIdentifier": None,
                "Engine": "postgres",
                "MultiAZ": True,
                "StorageEncrypted": True,
                "BackupRetentionPeriod": 7,
                "Endpoint": {"Address": "multi-az-db.xyz.rds.amazonaws.com", "Port": 5432},
                "AvailabilityZone": "ap-northeast-1a",
                "VpcSecurityGroups": [],
            }
        ]

        ec2 = _ec2_client_with_instances([])
        rds = _rds_client_with_clusters(clusters=[], instances=instances)
        session = _mock_boto3_session(ec2=ec2, rds=rds)
        mock_session_fn.return_value = session

        scanner = _make_scanner()
        result = scanner.scan()

        comp = result.graph.get_component("rds-multi-az-db")
        assert comp is not None
        assert comp.replicas == 2
        assert comp.failover.enabled is True


# ---------------------------------------------------------------------------
# Test: ECS task definition parsing
# ---------------------------------------------------------------------------

class TestECSTaskDefinitionParsing:
    @patch("faultray.discovery.aws_scanner._boto3_session")
    def test_ecs_env_var_dependency_inference(self, mock_session_fn):
        """ECS env vars referencing RDS endpoints should create dependencies."""
        instances = []
        ec2 = _ec2_client_with_instances(instances)

        # RDS instance
        rds_instances = [
            {
                "DBInstanceIdentifier": "ecs-db",
                "DBClusterIdentifier": None,
                "Engine": "postgres",
                "MultiAZ": False,
                "StorageEncrypted": False,
                "BackupRetentionPeriod": 1,
                "Endpoint": {"Address": "ecs-db.xyz.ap-northeast-1.rds.amazonaws.com", "Port": 5432},
                "AvailabilityZone": "ap-northeast-1a",
                "VpcSecurityGroups": [],
            }
        ]
        rds = _rds_client_with_clusters(clusters=[], instances=rds_instances)

        # ECS
        ecs = MagicMock()
        cluster_paginator = MagicMock()
        cluster_paginator.paginate.return_value = iter([
            {"clusterArns": ["arn:aws:ecs:ap-northeast-1:123456:cluster/prod"]}
        ])

        svc_paginator = MagicMock()
        svc_paginator.paginate.return_value = iter([
            {"serviceArns": ["arn:aws:ecs:ap-northeast-1:123456:service/prod/api"]}
        ])

        def _get_paginator(op):
            if op == "list_clusters":
                return cluster_paginator
            if op == "list_services":
                return svc_paginator
            return MagicMock()

        ecs.get_paginator.side_effect = _get_paginator

        ecs.describe_services.return_value = {
            "services": [
                {
                    "serviceName": "api",
                    "desiredCount": 2,
                    "runningCount": 2,
                    "taskDefinition": "arn:aws:ecs:ap-northeast-1:123456:task-definition/api:3",
                }
            ]
        }
        ecs.describe_task_definition.return_value = {
            "taskDefinition": {
                "containerDefinitions": [
                    {
                        "name": "api",
                        "environment": [
                            {
                                "name": "DATABASE_URL",
                                "value": "postgresql://user:pass@ecs-db.xyz.ap-northeast-1.rds.amazonaws.com:5432/mydb"
                            }
                        ],
                    }
                ]
            }
        }

        session = _mock_boto3_session(ec2=ec2, rds=rds, ecs=ecs)
        mock_session_fn.return_value = session

        scanner = _make_scanner()
        result = scanner.scan()

        # ECS service should exist
        ecs_comp = result.graph.get_component("ecs-prod-api")
        assert ecs_comp is not None
        assert ecs_comp.type == ComponentType.APP_SERVER

        # RDS should exist
        rds_comp = result.graph.get_component("rds-ecs-db")
        assert rds_comp is not None

        # Dependency should be inferred via env var
        edges = result.graph.all_dependency_edges()
        ecs_to_rds = [e for e in edges if "ecs-prod-api" in e.source_id and "rds-ecs-db" in e.target_id]
        assert len(ecs_to_rds) == 1
        assert ecs_to_rds[0].dependency_type == "requires"


# ---------------------------------------------------------------------------
# Test: Lambda discovery
# ---------------------------------------------------------------------------

class TestLambdaDiscovery:
    @patch("faultray.discovery.aws_scanner._boto3_session")
    def test_discover_lambda_functions(self, mock_session_fn):
        functions = [
            {
                "FunctionName": "order-processor",
                "MemorySize": 256,
                "Timeout": 30,
                "Runtime": "python3.12",
                "VpcConfig": {},
            }
        ]

        ec2 = _ec2_client_with_instances([])
        lam = _lambda_client_with_functions(functions)
        session = _mock_boto3_session(ec2=ec2, **{"lambda": lam})
        mock_session_fn.return_value = session

        scanner = _make_scanner()
        result = scanner.scan()

        comp = result.graph.get_component("lambda-order-processor")
        assert comp is not None
        assert comp.type == ComponentType.APP_SERVER
        assert comp.capacity.max_memory_mb == 256.0
        assert comp.capacity.timeout_seconds == 30.0
        assert comp.autoscaling.enabled is True  # Lambda always autoscales
        assert "lambda" in comp.tags


# ---------------------------------------------------------------------------
# Test: CloudFront discovery
# ---------------------------------------------------------------------------

class TestCloudFrontDiscovery:
    @patch("faultray.discovery.aws_scanner._boto3_session")
    def test_discover_cloudfront(self, mock_session_fn):
        distributions = [
            {
                "Id": "E1234ABCDE",
                "DomainName": "d111.cloudfront.net",
                "WebACLId": "arn:aws:wafv2:us-east-1:123:global/webacl/my-acl/abc",
            }
        ]

        ec2 = _ec2_client_with_instances([])
        cf = _cloudfront_client_with_dists(distributions)
        session = _mock_boto3_session(ec2=ec2, cloudfront=cf)
        mock_session_fn.return_value = session

        scanner = _make_scanner()
        result = scanner.scan()

        comp = result.graph.get_component("cloudfront-E1234ABCDE")
        assert comp is not None
        assert comp.type == ComponentType.LOAD_BALANCER
        assert comp.security.encryption_in_transit is True
        assert comp.security.waf_protected is True
        assert "cloudfront" in comp.tags


# ---------------------------------------------------------------------------
# Test: Complete scan flow (all services mocked)
# ---------------------------------------------------------------------------

class TestCompleteScanFlow:
    @patch("faultray.discovery.aws_scanner._boto3_session")
    def test_full_scan_integration(self, mock_session_fn):
        """Full scan with multiple service types, verifying component count and types."""
        instances = [
            {
                "InstanceId": "i-web1",
                "State": {"Name": "running"},
                "InstanceType": "t3.medium",
                "PrivateIpAddress": "10.0.1.1",
                "Placement": {"AvailabilityZone": "ap-northeast-1a"},
                "SubnetId": "subnet-a",
                "SecurityGroups": [{"GroupId": "sg-web"}],
                "Tags": [{"Key": "Name", "Value": "web-1"}],
            },
        ]
        ec2 = _ec2_client_with_instances(instances)

        rds_instances = [
            {
                "DBInstanceIdentifier": "main-db",
                "DBClusterIdentifier": None,
                "Engine": "postgres",
                "MultiAZ": True,
                "StorageEncrypted": True,
                "BackupRetentionPeriod": 7,
                "Endpoint": {"Address": "main-db.rds.amazonaws.com", "Port": 5432},
                "AvailabilityZone": "ap-northeast-1a",
                "VpcSecurityGroups": [],
            }
        ]
        rds = _rds_client_with_clusters(clusters=[], instances=rds_instances)

        lbs = [
            {
                "LoadBalancerName": "main-alb",
                "LoadBalancerArn": "arn:aws:elb:ap-northeast-1:123:lb/app/main-alb/x",
                "Type": "application",
                "DNSName": "main-alb.elb.amazonaws.com",
                "AvailabilityZones": [
                    {"ZoneName": "ap-northeast-1a"},
                    {"ZoneName": "ap-northeast-1c"},
                ],
                "SecurityGroups": [],
            }
        ]
        elbv2 = _elbv2_client_with_lbs(lbs)

        s3 = _s3_client_with_buckets(["static-assets"])
        sqs = _sqs_client_with_queues(["https://sqs.amazonaws.com/123/events"])

        cw = MagicMock()
        cw.get_metric_statistics.return_value = {"Datapoints": [{"Average": 25.0}]}

        session = _mock_boto3_session(ec2=ec2, rds=rds, elbv2=elbv2, s3=s3, sqs=sqs, cloudwatch=cw)
        mock_session_fn.return_value = session

        scanner = _make_scanner()
        result = scanner.scan()

        assert result.region == "ap-northeast-1"
        assert result.scan_duration_seconds >= 0
        assert result.components_found >= 5  # EC2 + RDS + ALB + S3 + SQS

        # Verify types present
        types_found = {c.type for c in result.graph.components.values()}
        assert ComponentType.APP_SERVER in types_found
        assert ComponentType.DATABASE in types_found
        assert ComponentType.LOAD_BALANCER in types_found
        assert ComponentType.STORAGE in types_found
        assert ComponentType.QUEUE in types_found

    @patch("faultray.discovery.aws_scanner._boto3_session")
    def test_scan_result_dataclass(self, mock_session_fn):
        """AWSDiscoveryResult fields are properly populated."""
        ec2 = _ec2_client_with_instances([])
        session = _mock_boto3_session(ec2=ec2)
        mock_session_fn.return_value = session

        scanner = _make_scanner(region="us-east-1", profile="test-profile")
        result = scanner.scan()

        assert result.region == "us-east-1"
        assert isinstance(result.graph, InfraGraph)
        assert isinstance(result.warnings, list)
        assert isinstance(result.scan_duration_seconds, float)


# ---------------------------------------------------------------------------
# Test: Route53 discovery
# ---------------------------------------------------------------------------

class TestRoute53Discovery:
    @patch("faultray.discovery.aws_scanner._boto3_session")
    def test_discover_route53_zones(self, mock_session_fn):
        ec2 = _ec2_client_with_instances([])

        r53 = MagicMock()
        r53.list_hosted_zones.return_value = {
            "HostedZones": [
                {
                    "Id": "/hostedzone/Z123ABC",
                    "Name": "example.com.",
                }
            ]
        }
        r53.list_resource_record_sets.return_value = {
            "ResourceRecordSets": [
                {
                    "Name": "api.example.com.",
                    "Type": "A",
                    "AliasTarget": {
                        "DNSName": "main-alb.elb.amazonaws.com.",
                    },
                }
            ]
        }

        session = _mock_boto3_session(ec2=ec2, route53=r53)
        mock_session_fn.return_value = session

        scanner = _make_scanner()
        result = scanner.scan()

        comp = result.graph.get_component("route53-Z123ABC")
        assert comp is not None
        assert comp.type == ComponentType.DNS
        assert "route53" in comp.tags


# ---------------------------------------------------------------------------
# Test: ElastiCache discovery
# ---------------------------------------------------------------------------

class TestElastiCacheDiscovery:
    @patch("faultray.discovery.aws_scanner._boto3_session")
    def test_discover_elasticache_replication_group(self, mock_session_fn):
        ec2 = _ec2_client_with_instances([])

        elasticache = MagicMock()
        rg_paginator = MagicMock()
        rg_paginator.paginate.return_value = iter([
            {
                "ReplicationGroups": [
                    {
                        "ReplicationGroupId": "prod-redis",
                        "MultiAZ": "enabled",
                        "AutomaticFailover": "enabled",
                        "AtRestEncryptionEnabled": True,
                        "TransitEncryptionEnabled": True,
                        "NodeGroups": [
                            {
                                "NodeGroupMembers": [
                                    {"CacheNodeId": "0001"},
                                    {"CacheNodeId": "0002"},
                                ]
                            }
                        ],
                    }
                ]
            }
        ])

        cc_paginator = MagicMock()
        cc_paginator.paginate.return_value = iter([{"CacheClusters": []}])

        def _get_paginator(op):
            if op == "describe_replication_groups":
                return rg_paginator
            if op == "describe_cache_clusters":
                return cc_paginator
            return MagicMock()

        elasticache.get_paginator.side_effect = _get_paginator

        session = _mock_boto3_session(ec2=ec2, elasticache=elasticache)
        mock_session_fn.return_value = session

        scanner = _make_scanner()
        result = scanner.scan()

        comp = result.graph.get_component("elasticache-prod-redis")
        assert comp is not None
        assert comp.type == ComponentType.CACHE
        assert comp.replicas == 2
        assert comp.failover.enabled is True
        assert comp.security.encryption_at_rest is True
        assert comp.security.encryption_in_transit is True
