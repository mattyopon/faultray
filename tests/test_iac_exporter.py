"""Tests for Multi-Format IaC Export Engine."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
)
from faultray.model.graph import InfraGraph
from faultray.remediation.iac_exporter import (
    IaCExporter,
    IaCExportResult,
    IaCFormat,
    _sanitize_id,
    _sanitize_k8s_name,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_component(
    cid: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    port: int = 8080,
    replicas: int = 1,
    autoscaling: AutoScalingConfig | None = None,
    failover: FailoverConfig | None = None,
) -> Component:
    return Component(
        id=cid,
        name=cid.replace("_", " ").title(),
        type=ctype,
        port=port,
        replicas=replicas,
        autoscaling=autoscaling or AutoScalingConfig(),
        failover=failover or FailoverConfig(),
    )


def _simple_graph(
    components: list[Component],
    deps: list[tuple[str, str]] | None = None,
) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for src, tgt in deps or []:
        g.add_dependency(Dependency(source_id=src, target_id=tgt))
    return g


def _web_app_graph() -> InfraGraph:
    """Build a typical web app graph: LB -> web -> app -> db, cache, queue."""
    lb = _make_component("lb", ComponentType.LOAD_BALANCER, port=80, replicas=2)
    web = _make_component("web", ComponentType.WEB_SERVER, port=80, replicas=2)
    api = _make_component("api", ComponentType.APP_SERVER, port=8080, replicas=3,
                          autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10))
    db = _make_component("postgres", ComponentType.DATABASE, port=5432, replicas=2)
    cache = _make_component("redis", ComponentType.CACHE, port=6379, replicas=2)
    queue = _make_component("rabbitmq", ComponentType.QUEUE, port=5672)
    storage = _make_component("s3", ComponentType.STORAGE, port=9000)

    return _simple_graph(
        [lb, web, api, db, cache, queue, storage],
        [
            ("lb", "web"),
            ("web", "api"),
            ("api", "postgres"),
            ("api", "redis"),
            ("api", "rabbitmq"),
            ("api", "s3"),
        ],
    )


# ---------------------------------------------------------------------------
# Sanitisation helpers
# ---------------------------------------------------------------------------

class TestSanitization:
    def test_sanitize_id_basic(self):
        assert _sanitize_id("my-server") == "my_server"

    def test_sanitize_id_special_chars(self):
        assert _sanitize_id("web.server.01") == "web_server_01"

    def test_sanitize_k8s_name(self):
        assert _sanitize_k8s_name("My_Server") == "my-server"

    def test_sanitize_k8s_strips_invalid(self):
        assert _sanitize_k8s_name("web@server!01") == "web-server-01"


# ---------------------------------------------------------------------------
# IaCFormat enum
# ---------------------------------------------------------------------------

class TestIaCFormat:
    def test_all_formats_exist(self):
        assert len(IaCFormat) == 6
        assert IaCFormat.TERRAFORM.value == "terraform"
        assert IaCFormat.CLOUDFORMATION.value == "cloudformation"
        assert IaCFormat.KUBERNETES.value == "kubernetes"
        assert IaCFormat.DOCKER_COMPOSE.value == "docker_compose"
        assert IaCFormat.ANSIBLE.value == "ansible"
        assert IaCFormat.PULUMI_PYTHON.value == "pulumi_python"


# ---------------------------------------------------------------------------
# Terraform export
# ---------------------------------------------------------------------------

class TestTerraformExport:
    def test_export_produces_main_tf(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export(graph, IaCFormat.TERRAFORM)

        assert result.format == IaCFormat.TERRAFORM
        assert "main.tf" in result.files
        assert len(result.files["main.tf"]) > 0

    def test_terraform_contains_provider(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_terraform(graph)
        content = result.files["main.tf"]
        assert 'provider "aws"' in content

    def test_terraform_contains_all_components(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_terraform(graph)
        content = result.files["main.tf"]
        # Check each component type is represented
        assert "aws_lb" in content  # LB
        assert "aws_ecs_service" in content  # Server
        assert "aws_rds_cluster" in content  # Database
        assert "aws_elasticache" in content  # Cache
        assert "aws_sqs_queue" in content  # Queue
        assert "aws_s3_bucket" in content  # Storage

    def test_terraform_managed_by_tag(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_terraform(graph)
        content = result.files["main.tf"]
        assert "faultzero" in content

    def test_terraform_autoscaling_when_enabled(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_terraform(graph)
        content = result.files["main.tf"]
        assert "aws_appautoscaling" in content

    def test_terraform_has_security_groups(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_terraform(graph)
        content = result.files["main.tf"]
        assert "aws_security_group" in content

    def test_terraform_readme(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_terraform(graph)
        assert "terraform init" in result.readme
        assert "terraform apply" in result.readme


# ---------------------------------------------------------------------------
# CloudFormation export
# ---------------------------------------------------------------------------

class TestCloudFormationExport:
    def test_export_produces_template(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export(graph, IaCFormat.CLOUDFORMATION)

        assert result.format == IaCFormat.CLOUDFORMATION
        assert "template.yaml" in result.files

    def test_cfn_has_template_version(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_cloudformation(graph)
        content = result.files["template.yaml"]
        assert "AWSTemplateFormatVersion" in content

    def test_cfn_has_parameters(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_cloudformation(graph)
        content = result.files["template.yaml"]
        assert "Parameters:" in content
        assert "VpcId:" in content

    def test_cfn_contains_resources(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_cloudformation(graph)
        content = result.files["template.yaml"]
        assert "Resources:" in content
        assert "managed-by" in content


# ---------------------------------------------------------------------------
# Kubernetes export
# ---------------------------------------------------------------------------

class TestKubernetesExport:
    def test_export_produces_multiple_files(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export(graph, IaCFormat.KUBERNETES)

        assert result.format == IaCFormat.KUBERNETES
        assert len(result.files) > 1
        assert "00-namespace.yaml" in result.files

    def test_k8s_namespace_file(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_kubernetes(graph)
        ns = result.files["00-namespace.yaml"]
        assert "kind: Namespace" in ns
        assert "faultzero" in ns

    def test_k8s_deployment_for_servers(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_kubernetes(graph)
        # Web server should have a Deployment
        assert "web.yaml" in result.files
        content = result.files["web.yaml"]
        assert "kind: Deployment" in content
        assert "kind: Service" in content

    def test_k8s_statefulset_for_database(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_kubernetes(graph)
        assert "postgres.yaml" in result.files
        content = result.files["postgres.yaml"]
        assert "kind: StatefulSet" in content

    def test_k8s_hpa_for_autoscaling(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_kubernetes(graph)
        # API has autoscaling enabled
        assert "api.yaml" in result.files
        content = result.files["api.yaml"]
        assert "HorizontalPodAutoscaler" in content

    def test_k8s_loadbalancer_ingress(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_kubernetes(graph)
        assert "lb.yaml" in result.files
        content = result.files["lb.yaml"]
        assert "kind: Ingress" in content


# ---------------------------------------------------------------------------
# Docker Compose export
# ---------------------------------------------------------------------------

class TestDockerComposeExport:
    def test_export_produces_compose_file(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export(graph, IaCFormat.DOCKER_COMPOSE)

        assert result.format == IaCFormat.DOCKER_COMPOSE
        assert "docker-compose.yml" in result.files

    def test_compose_has_services(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_docker_compose(graph)
        content = result.files["docker-compose.yml"]
        assert "services:" in content
        assert "networks:" in content

    def test_compose_healthcheck(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_docker_compose(graph)
        content = result.files["docker-compose.yml"]
        assert "healthcheck:" in content

    def test_compose_volumes_for_stateful(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_docker_compose(graph)
        content = result.files["docker-compose.yml"]
        assert "volumes:" in content

    def test_compose_managed_by_label(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_docker_compose(graph)
        content = result.files["docker-compose.yml"]
        assert "faultzero" in content


# ---------------------------------------------------------------------------
# Ansible export
# ---------------------------------------------------------------------------

class TestAnsibleExport:
    def test_export_produces_playbook(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export(graph, IaCFormat.ANSIBLE)

        assert result.format == IaCFormat.ANSIBLE
        assert "playbook.yml" in result.files

    def test_ansible_has_docker_tasks(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_ansible(graph)
        content = result.files["playbook.yml"]
        assert "docker_container" in content
        assert "faultzero" in content

    def test_ansible_install_docker(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_ansible(graph)
        content = result.files["playbook.yml"]
        assert "docker.io" in content


# ---------------------------------------------------------------------------
# Pulumi export
# ---------------------------------------------------------------------------

class TestPulumiExport:
    def test_export_produces_main_py(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export(graph, IaCFormat.PULUMI_PYTHON)

        assert result.format == IaCFormat.PULUMI_PYTHON
        assert "__main__.py" in result.files

    def test_pulumi_imports(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_pulumi(graph)
        content = result.files["__main__.py"]
        assert "import pulumi" in content
        assert "import pulumi_aws" in content

    def test_pulumi_common_tags(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_pulumi(graph)
        content = result.files["__main__.py"]
        assert "faultzero" in content
        assert "common_tags" in content

    def test_pulumi_database_resource(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_pulumi(graph)
        content = result.files["__main__.py"]
        assert "aws.rds.Cluster" in content

    def test_pulumi_cache_resource(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_pulumi(graph)
        content = result.files["__main__.py"]
        assert "aws.elasticache.ReplicationGroup" in content

    def test_pulumi_queue_resource(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_pulumi(graph)
        content = result.files["__main__.py"]
        assert "aws.sqs.Queue" in content


# ---------------------------------------------------------------------------
# Dispatch and general
# ---------------------------------------------------------------------------

class TestExportDispatch:
    def test_export_dispatches_correctly(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        for fmt in IaCFormat:
            result = exporter.export(graph, fmt)
            assert result.format == fmt
            assert len(result.files) > 0

    def test_empty_graph_produces_files(self):
        graph = InfraGraph()
        exporter = IaCExporter()
        result = exporter.export_terraform(graph)
        assert "main.tf" in result.files

    def test_single_component_graph(self):
        comp = _make_component("web", ComponentType.WEB_SERVER, port=80)
        graph = _simple_graph([comp])
        exporter = IaCExporter()
        result = exporter.export_terraform(graph)
        assert "main.tf" in result.files
        assert "web" in result.files["main.tf"].lower()


# ---------------------------------------------------------------------------
# Remediation export
# ---------------------------------------------------------------------------

class TestRemediationExport:
    def test_remediation_export_adds_warnings(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        changes = [
            {"component_id": "postgres", "action": "add_replicas", "replicas": 3},
        ]
        result = exporter.export_remediation(graph, changes, IaCFormat.TERRAFORM)
        assert any("Remediation applied" in w for w in result.warnings)

    def test_remediation_export_empty_changes(self):
        graph = _web_app_graph()
        exporter = IaCExporter()
        result = exporter.export_remediation(graph, [], IaCFormat.KUBERNETES)
        assert result.format == IaCFormat.KUBERNETES
        assert len(result.files) > 0


# ---------------------------------------------------------------------------
# DNS component
# ---------------------------------------------------------------------------

class TestDNSExport:
    def test_terraform_dns(self):
        dns = _make_component("dns", ComponentType.DNS, port=53)
        graph = _simple_graph([dns])
        exporter = IaCExporter()
        result = exporter.export_terraform(graph)
        content = result.files["main.tf"]
        assert "aws_route53" in content

    def test_kubernetes_dns(self):
        dns = _make_component("dns", ComponentType.DNS, port=53)
        graph = _simple_graph([dns])
        exporter = IaCExporter()
        result = exporter.export_kubernetes(graph)
        assert "dns.yaml" in result.files
