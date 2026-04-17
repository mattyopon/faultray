# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Tests for new infrastructure scanners: Sakura, Alibaba, OCI, OnPrem.

All SDK calls are mocked — tests work without actual cloud credentials or
third-party SDK packages installed.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Sample test data
# ---------------------------------------------------------------------------

SAMPLE_CSV = textwrap.dedent("""\
    hostname,ip_address,role,os
    web-01,10.0.1.10,web_server,ubuntu
    db-01,10.0.1.20,database,centos
    cache-01,10.0.1.30,cache,ubuntu
""")

SAMPLE_JSON = {
    "hosts": [
        {"hostname": "web-01", "ip": "10.0.1.10", "role": "web_server"},
        {"hostname": "db-01", "ip": "10.0.1.20", "role": "database"},
    ]
}

SAMPLE_NMAP_XML = textwrap.dedent("""\
    <?xml version="1.0"?>
    <nmaprun>
      <host>
        <status state="up"/>
        <address addr="10.0.1.10" addrtype="ipv4"/>
        <ports>
          <port portid="80"><state state="open"/><service name="http"/></port>
          <port portid="443"><state state="open"/><service name="https"/></port>
        </ports>
      </host>
      <host>
        <status state="up"/>
        <address addr="10.0.1.20" addrtype="ipv4"/>
        <ports>
          <port portid="3306"><state state="open"/><service name="mysql"/></port>
        </ports>
      </host>
    </nmaprun>
""")


# ===========================================================================
# SakuraScanner
# ===========================================================================

class TestSakuraScannerInstantiation:
    """SakuraScanner can be imported and instantiated without the requests SDK."""

    def test_import_without_requests(self):
        """Module import succeeds even when 'requests' is absent."""
        saved = sys.modules.pop("requests", None)
        try:
            # Remove any cached import of the scanner module so it re-evaluates
            sys.modules.pop("faultray.discovery.sakura_scanner", None)
            from faultray.discovery.sakura_scanner import SakuraScanner
            scanner = SakuraScanner(token="t", secret="s", zone="tk1v")
            assert scanner.zone == "tk1v"
        finally:
            if saved is not None:
                sys.modules["requests"] = saved

    def test_default_zone(self):
        from faultray.discovery.sakura_scanner import SakuraScanner
        scanner = SakuraScanner(token="t", secret="s")
        assert scanner.zone == "tk1v"

    def test_custom_zone(self):
        from faultray.discovery.sakura_scanner import SakuraScanner
        scanner = SakuraScanner(token="t", secret="s", zone="is1b")
        assert scanner.zone == "is1b"

    def test_scan_raises_without_requests(self):
        """scan() raises RuntimeError when 'requests' is not installed."""
        with patch.dict(sys.modules, {"requests": None}):
            sys.modules.pop("faultray.discovery.sakura_scanner", None)
            from faultray.discovery.sakura_scanner import SakuraScanner
            scanner = SakuraScanner(token="t", secret="s")
            with pytest.raises(RuntimeError, match="requests is required"):
                scanner.scan()

    def test_type_map_contains_expected_keys(self):
        from faultray.discovery.sakura_scanner import SAKURA_TYPE_MAP
        assert "server" in SAKURA_TYPE_MAP
        assert "load_balancer" in SAKURA_TYPE_MAP
        assert "database" in SAKURA_TYPE_MAP


class TestSakuraScannerWithMocks:
    """SakuraScanner.scan() with mocked HTTP session."""

    def _make_scanner(self):
        from faultray.discovery.sakura_scanner import SakuraScanner
        return SakuraScanner(token="tok", secret="sec", zone="tk1v")

    def _make_mock_session(self, responses: dict[str, dict]):
        """Create a mock requests.Session that returns pre-built responses."""
        session = MagicMock()

        def _get(url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status.return_value = None
            for key, payload in responses.items():
                if key in url:
                    resp.json.return_value = payload
                    return resp
            resp.json.return_value = {}
            return resp

        session.get.side_effect = _get
        return session

    def test_scan_returns_discovery_result_type(self):
        from faultray.discovery.sakura_scanner import SakuraDiscoveryResult, SakuraScanner

        mock_requests = MagicMock()
        mock_session = self._make_mock_session({
            "server": {"Servers": []},
            "disk": {"Disks": []},
            "loadbalancer": {"LoadBalancers": []},
            "database": {"Databases": []},
            "switch": {"Switches": []},
            "vpcrouter": {"VPCRouters": []},
        })
        mock_requests.Session.return_value = mock_session

        with patch.dict(sys.modules, {"requests": mock_requests}):
            scanner = SakuraScanner(token="t", secret="s", zone="tk1v")
            result = scanner.scan()

        assert isinstance(result, SakuraDiscoveryResult)
        assert isinstance(result.graph, InfraGraph)
        assert result.zone == "tk1v"

    def test_scan_discovers_servers(self):
        from faultray.discovery.sakura_scanner import SakuraScanner

        servers_payload = {
            "Servers": [
                {
                    "ID": "123456789012",
                    "Name": "web-server-01",
                    "Availability": "available",
                    "Interfaces": [{"IPAddress": "10.0.1.10", "Switch": {}}],
                    "ServerPlan": {"CPU": 2, "MemoryMB": 4096},
                }
            ]
        }
        mock_requests = MagicMock()
        mock_session = self._make_mock_session({
            "server": servers_payload,
            "disk": {"Disks": []},
            "loadbalancer": {"LoadBalancers": []},
            "database": {"Databases": []},
            "switch": {"Switches": []},
            "vpcrouter": {"VPCRouters": []},
        })
        mock_requests.Session.return_value = mock_session

        with patch.dict(sys.modules, {"requests": mock_requests}):
            scanner = SakuraScanner(token="t", secret="s", zone="tk1v")
            result = scanner.scan()

        assert result.components_found == 1
        comp_id = "sakura-server-123456789012"
        assert comp_id in result.graph.components
        comp = result.graph.components[comp_id]
        assert comp.type == ComponentType.APP_SERVER
        assert comp.host == "10.0.1.10"

    def test_scan_empty_environment(self):
        from faultray.discovery.sakura_scanner import SakuraScanner

        mock_requests = MagicMock()
        mock_session = self._make_mock_session({
            "server": {"Servers": []},
            "disk": {"Disks": []},
            "loadbalancer": {"LoadBalancers": []},
            "database": {"Databases": []},
            "switch": {"Switches": []},
            "vpcrouter": {"VPCRouters": []},
        })
        mock_requests.Session.return_value = mock_session

        with patch.dict(sys.modules, {"requests": mock_requests}):
            scanner = SakuraScanner(token="t", secret="s", zone="tk1v")
            result = scanner.scan()

        assert result.components_found == 0
        assert result.dependencies_inferred == 0
        assert result.scan_duration_seconds >= 0.0

    def test_scan_skips_unavailable_servers(self):
        from faultray.discovery.sakura_scanner import SakuraScanner

        servers_payload = {
            "Servers": [
                {
                    "ID": "111",
                    "Name": "stopped-server",
                    "Availability": "stopped",  # should be skipped
                    "Interfaces": [],
                    "ServerPlan": {"CPU": 1, "MemoryMB": 1024},
                }
            ]
        }
        mock_requests = MagicMock()
        mock_session = self._make_mock_session({
            "server": servers_payload,
            "disk": {"Disks": []},
            "loadbalancer": {"LoadBalancers": []},
            "database": {"Databases": []},
            "switch": {"Switches": []},
            "vpcrouter": {"VPCRouters": []},
        })
        mock_requests.Session.return_value = mock_session

        with patch.dict(sys.modules, {"requests": mock_requests}):
            scanner = SakuraScanner(token="t", secret="s")
            result = scanner.scan()

        assert result.components_found == 0

    def test_scan_infers_lb_to_server_dependency(self):
        """LB and server on same switch get a dependency edge."""
        from faultray.discovery.sakura_scanner import SakuraScanner

        sw_id = "SW001"
        mock_requests = MagicMock()
        mock_session = self._make_mock_session({
            "server": {"Servers": [
                {
                    "ID": "SRV1",
                    "Name": "app-server",
                    "Availability": "available",
                    "Interfaces": [{"IPAddress": "10.0.0.1", "Switch": {"ID": sw_id}}],
                    "ServerPlan": {"CPU": 1, "MemoryMB": 1024},
                }
            ]},
            "disk": {"Disks": []},
            "loadbalancer": {"LoadBalancers": [
                {
                    "ID": "LB1",
                    "Name": "my-lb",
                    "Remark": {"Servers": [{"IPAddress": "10.0.0.100"}]},
                    "Interfaces": [{"Switch": {"ID": sw_id}}],
                }
            ]},
            "database": {"Databases": []},
            "switch": {"Switches": []},
            "vpcrouter": {"VPCRouters": []},
        })
        mock_requests.Session.return_value = mock_session

        with patch.dict(sys.modules, {"requests": mock_requests}):
            scanner = SakuraScanner(token="t", secret="s")
            result = scanner.scan()

        assert result.components_found == 2
        assert result.dependencies_inferred >= 1


# ===========================================================================
# AlibabaScanner
# ===========================================================================

class TestAlibabaScannerInstantiation:
    """AlibabaScanner can be imported and instantiated without the Alibaba SDK."""

    def test_import_without_sdk(self):
        """Module import succeeds even when alibabacloud SDK is absent."""
        sys.modules.pop("faultray.discovery.alibaba_scanner", None)
        from faultray.discovery.alibaba_scanner import AlibabaScanner
        scanner = AlibabaScanner(
            access_key_id="key",
            access_key_secret="secret",
            region="cn-hangzhou",
        )
        assert scanner.region == "cn-hangzhou"

    def test_default_region(self):
        from faultray.discovery.alibaba_scanner import AlibabaScanner
        scanner = AlibabaScanner(access_key_id="k", access_key_secret="s")
        assert scanner.region == "cn-hangzhou"

    def test_scan_raises_without_alibaba_sdk(self):
        """scan() raises RuntimeError when alibabacloud SDK is not installed."""
        with patch.dict(sys.modules, {"alibabacloud_ecs20140526": None}):
            sys.modules.pop("faultray.discovery.alibaba_scanner", None)
            from faultray.discovery.alibaba_scanner import AlibabaScanner
            scanner = AlibabaScanner(access_key_id="k", access_key_secret="s")
            with pytest.raises(RuntimeError, match="alibabacloud-ecs20140526"):
                scanner.scan()

    def test_type_map_contains_expected_keys(self):
        from faultray.discovery.alibaba_scanner import ALIBABA_TYPE_MAP
        assert "ecs" in ALIBABA_TYPE_MAP
        assert "rds" in ALIBABA_TYPE_MAP
        assert "slb" in ALIBABA_TYPE_MAP
        assert "redis" in ALIBABA_TYPE_MAP

    def test_vpc_id_filter_stored(self):
        from faultray.discovery.alibaba_scanner import AlibabaScanner
        scanner = AlibabaScanner(
            access_key_id="k",
            access_key_secret="s",
            vpc_id="vpc-123",
        )
        assert scanner.vpc_id == "vpc-123"


class TestAlibabaScannerReturnType:
    """AlibabaScanner.scan() returns AlibabaDiscoveryResult with correct shape."""

    def _mock_alibaba_sdk(self):
        """Set up sys.modules mocks for all alibabacloud SDK packages."""
        mock_ecs_module = MagicMock()
        mock_rds_module = MagicMock()
        mock_slb_module = MagicMock()
        mock_tea = MagicMock()

        # ECS client: describe_instances returns empty page
        ecs_client = MagicMock()
        ecs_resp = MagicMock()
        ecs_resp.body.instances.instance = []
        ecs_resp.body.total_count = 0
        ecs_client.describe_instances.return_value = ecs_resp
        mock_ecs_module.client.Client.return_value = ecs_client

        # RDS client: describe_db_instances returns empty page
        rds_client = MagicMock()
        rds_resp = MagicMock()
        rds_resp.body.items.db_instance = []
        rds_resp.body.total_record_count = 0
        rds_client.describe_db_instances.return_value = rds_resp
        mock_rds_module.client.Client.return_value = rds_client

        # SLB client: describe_load_balancers returns empty page
        slb_client = MagicMock()
        slb_resp = MagicMock()
        slb_resp.body.load_balancers.load_balancer = []
        slb_resp.body.total_count = 0
        slb_client.describe_load_balancers.return_value = slb_resp
        mock_slb_module.client.Client.return_value = slb_client

        # requests mock: redis / oss / vpc all return non-200
        mock_requests = MagicMock()
        non_200 = MagicMock()
        non_200.status_code = 403
        mock_requests.get.return_value = non_200

        return {
            "alibabacloud_ecs20140526": mock_ecs_module,
            "alibabacloud_ecs20140526.client": mock_ecs_module.client,
            "alibabacloud_rds20140815": mock_rds_module,
            "alibabacloud_rds20140815.client": mock_rds_module.client,
            "alibabacloud_slb20140515": mock_slb_module,
            "alibabacloud_slb20140515.client": mock_slb_module.client,
            "alibabacloud_tea_openapi": mock_tea,
            "alibabacloud_tea_openapi.models": mock_tea.models,
            "requests": mock_requests,
        }

    def test_scan_returns_discovery_result_type(self):
        from faultray.discovery.alibaba_scanner import AlibabaDiscoveryResult, AlibabaScanner

        mocks = self._mock_alibaba_sdk()
        with patch.dict(sys.modules, mocks):
            sys.modules.pop("faultray.discovery.alibaba_scanner", None)
            from faultray.discovery.alibaba_scanner import AlibabaScanner as AS2
            scanner = AS2(access_key_id="k", access_key_secret="s")
            result = scanner.scan()

        assert isinstance(result.graph, InfraGraph)
        assert result.region == "cn-hangzhou"
        assert isinstance(result.warnings, list)
        assert result.scan_duration_seconds >= 0.0

    def test_scan_empty_environment_has_zero_components(self):
        mocks = self._mock_alibaba_sdk()
        with patch.dict(sys.modules, mocks):
            sys.modules.pop("faultray.discovery.alibaba_scanner", None)
            from faultray.discovery.alibaba_scanner import AlibabaScanner as AS2
            scanner = AS2(access_key_id="k", access_key_secret="s")
            result = scanner.scan()

        assert result.components_found == 0
        assert result.dependencies_inferred == 0


# ===========================================================================
# OCIScanner
# ===========================================================================

class TestOCIScannerInstantiation:
    """OCIScanner can be imported and instantiated without the OCI SDK."""

    def test_import_without_oci_sdk(self):
        sys.modules.pop("faultray.discovery.oci_scanner", None)
        from faultray.discovery.oci_scanner import OCIScanner
        scanner = OCIScanner(compartment_id="ocid1.compartment.oc1..abc")
        assert scanner.compartment_id == "ocid1.compartment.oc1..abc"

    def test_scan_raises_without_oci_sdk(self):
        """scan() raises RuntimeError when OCI SDK is not installed."""
        with patch.dict(sys.modules, {"oci": None}):
            sys.modules.pop("faultray.discovery.oci_scanner", None)
            from faultray.discovery.oci_scanner import OCIScanner
            scanner = OCIScanner(compartment_id="ocid1.compartment.oc1..abc")
            with pytest.raises(RuntimeError, match="oci is required"):
                scanner.scan()

    def test_profile_and_region_stored(self):
        from faultray.discovery.oci_scanner import OCIScanner
        scanner = OCIScanner(
            compartment_id="ocid1.compartment.oc1..abc",
            profile="MYPROFILE",
            region="ap-tokyo-1",
        )
        assert scanner.profile == "MYPROFILE"
        assert scanner.region == "ap-tokyo-1"

    def test_type_map_contains_expected_keys(self):
        from faultray.discovery.oci_scanner import OCI_TYPE_MAP
        assert "compute" in OCI_TYPE_MAP
        assert "db_system" in OCI_TYPE_MAP
        assert "load_balancer" in OCI_TYPE_MAP
        assert "object_storage" in OCI_TYPE_MAP


class TestOCIScannerReturnType:
    """OCIScanner.scan() returns OCIDiscoveryResult with correct shape."""

    def _mock_oci_sdk(self):
        """Set up a minimal OCI SDK mock that returns empty results."""
        mock_oci = MagicMock()

        # config.from_file returns a simple dict
        mock_oci.config.from_file.return_value = {"region": "us-ashburn-1"}

        # pagination.list_call_get_all_results returns empty data
        empty_result = MagicMock()
        empty_result.data = []
        mock_oci.pagination.list_call_get_all_results.return_value = empty_result

        # get_namespace returns a string
        ns_result = MagicMock()
        ns_result.data = "myns"
        mock_oci.object_storage.ObjectStorageClient.return_value.get_namespace.return_value = ns_result

        return {"oci": mock_oci}

    def test_scan_returns_oci_discovery_result(self):
        mocks = self._mock_oci_sdk()
        with patch.dict(sys.modules, mocks):
            sys.modules.pop("faultray.discovery.oci_scanner", None)
            from faultray.discovery.oci_scanner import OCIDiscoveryResult, OCIScanner
            scanner = OCIScanner(
                compartment_id="ocid1.compartment.oc1..abc",
                region="us-ashburn-1",
            )
            result = scanner.scan()

        assert isinstance(result, OCIDiscoveryResult)
        assert isinstance(result.graph, InfraGraph)
        assert result.compartment_id == "ocid1.compartment.oc1..abc"

    def test_scan_empty_environment(self):
        mocks = self._mock_oci_sdk()
        with patch.dict(sys.modules, mocks):
            sys.modules.pop("faultray.discovery.oci_scanner", None)
            from faultray.discovery.oci_scanner import OCIScanner
            scanner = OCIScanner(
                compartment_id="ocid1.compartment.oc1..abc",
                region="us-ashburn-1",
            )
            result = scanner.scan()

        assert result.components_found == 0
        assert result.dependencies_inferred == 0
        assert result.scan_duration_seconds >= 0.0


# ===========================================================================
# OnPremScanner — CSV
# ===========================================================================

class TestOnPremScannerCSV:
    """OnPremScanner can parse a CSV file to produce an InfraGraph."""

    def test_csv_creates_expected_component_count(self, tmp_path):
        from faultray.discovery.onprem_scanner import OnPremScanner

        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text(SAMPLE_CSV)

        scanner = OnPremScanner.from_cmdb_csv(csv_file)
        result = scanner.scan()

        assert result.components_found == 3

    def test_csv_component_types_inferred_correctly(self, tmp_path):
        from faultray.discovery.onprem_scanner import OnPremScanner

        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text(SAMPLE_CSV)

        scanner = OnPremScanner.from_cmdb_csv(csv_file)
        result = scanner.scan()

        types = {comp.type for comp in result.graph.components.values()}
        assert ComponentType.WEB_SERVER in types
        assert ComponentType.DATABASE in types
        assert ComponentType.CACHE in types

    def test_csv_hosts_parsed(self, tmp_path):
        from faultray.discovery.onprem_scanner import OnPremScanner

        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text(SAMPLE_CSV)

        scanner = OnPremScanner.from_cmdb_csv(csv_file)
        result = scanner.scan()

        hosts = {comp.host for comp in result.graph.components.values()}
        assert "10.0.1.10" in hosts
        assert "10.0.1.20" in hosts
        assert "10.0.1.30" in hosts

    def test_csv_names_parsed(self, tmp_path):
        from faultray.discovery.onprem_scanner import OnPremScanner

        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text(SAMPLE_CSV)

        scanner = OnPremScanner.from_cmdb_csv(csv_file)
        result = scanner.scan()

        names = {comp.name for comp in result.graph.components.values()}
        assert "web-01" in names
        assert "db-01" in names
        assert "cache-01" in names

    def test_csv_returns_onprem_discovery_result_type(self, tmp_path):
        from faultray.discovery.onprem_scanner import OnPremDiscoveryResult, OnPremScanner

        csv_file = tmp_path / "inventory.csv"
        csv_file.write_text(SAMPLE_CSV)

        scanner = OnPremScanner.from_cmdb_csv(csv_file)
        result = scanner.scan()

        assert isinstance(result, OnPremDiscoveryResult)
        assert isinstance(result.graph, InfraGraph)

    def test_csv_missing_file_raises_file_not_found(self, tmp_path):
        from faultray.discovery.onprem_scanner import OnPremScanner

        scanner = OnPremScanner.from_cmdb_csv(tmp_path / "nonexistent.csv")
        result = scanner.scan()
        # scan() catches exceptions and logs to warnings; check warnings or components == 0
        assert result.components_found == 0
        assert len(result.warnings) > 0

    def test_csv_infers_dependencies_between_components(self, tmp_path):
        from faultray.discovery.onprem_scanner import OnPremScanner

        # Use a minimal CSV with LB -> web -> db in same region
        csv_content = textwrap.dedent("""\
            hostname,ip_address,role
            lb-01,10.0.1.1,load_balancer
            web-01,10.0.1.2,web_server
            db-01,10.0.1.3,database
        """)
        csv_file = tmp_path / "topo.csv"
        csv_file.write_text(csv_content)

        scanner = OnPremScanner.from_cmdb_csv(csv_file)
        result = scanner.scan()

        # lb->web and web->db should be inferred
        assert result.dependencies_inferred >= 2


# ===========================================================================
# OnPremScanner — JSON
# ===========================================================================

class TestOnPremScannerJSON:
    """OnPremScanner can parse a JSON file to produce an InfraGraph."""

    def test_json_creates_expected_component_count(self, tmp_path):
        from faultray.discovery.onprem_scanner import OnPremScanner

        json_file = tmp_path / "inventory.json"
        json_file.write_text(json.dumps(SAMPLE_JSON))

        scanner = OnPremScanner.from_cmdb_json(json_file)
        result = scanner.scan()

        assert result.components_found == 2

    def test_json_component_types_inferred(self, tmp_path):
        from faultray.discovery.onprem_scanner import OnPremScanner

        json_file = tmp_path / "inventory.json"
        json_file.write_text(json.dumps(SAMPLE_JSON))

        scanner = OnPremScanner.from_cmdb_json(json_file)
        result = scanner.scan()

        types = {comp.type for comp in result.graph.components.values()}
        assert ComponentType.WEB_SERVER in types
        assert ComponentType.DATABASE in types

    def test_json_hosts_parsed(self, tmp_path):
        from faultray.discovery.onprem_scanner import OnPremScanner

        json_file = tmp_path / "inventory.json"
        json_file.write_text(json.dumps(SAMPLE_JSON))

        scanner = OnPremScanner.from_cmdb_json(json_file)
        result = scanner.scan()

        hosts = {comp.host for comp in result.graph.components.values()}
        assert "10.0.1.10" in hosts
        assert "10.0.1.20" in hosts

    def test_json_flat_list_format(self, tmp_path):
        """JSON as a flat list (not nested under 'hosts') works too."""
        from faultray.discovery.onprem_scanner import OnPremScanner

        data = [
            {"name": "srv-01", "ip": "192.168.1.1", "role": "app_server"},
            {"name": "db-01", "ip": "192.168.1.2", "role": "database"},
        ]
        json_file = tmp_path / "flat.json"
        json_file.write_text(json.dumps(data))

        scanner = OnPremScanner.from_cmdb_json(json_file)
        result = scanner.scan()

        assert result.components_found == 2

    def test_json_returns_onprem_discovery_result_type(self, tmp_path):
        from faultray.discovery.onprem_scanner import OnPremDiscoveryResult, OnPremScanner

        json_file = tmp_path / "inventory.json"
        json_file.write_text(json.dumps(SAMPLE_JSON))

        scanner = OnPremScanner.from_cmdb_json(json_file)
        result = scanner.scan()

        assert isinstance(result, OnPremDiscoveryResult)
        assert isinstance(result.graph, InfraGraph)

    def test_json_missing_file_produces_warning(self, tmp_path):
        from faultray.discovery.onprem_scanner import OnPremScanner

        scanner = OnPremScanner.from_cmdb_json(tmp_path / "no_such_file.json")
        result = scanner.scan()

        assert result.components_found == 0
        assert len(result.warnings) > 0

    def test_json_security_flags_parsed(self, tmp_path):
        """JSON items with security keys are correctly parsed."""
        from faultray.discovery.onprem_scanner import OnPremScanner

        data = [
            {
                "name": "secure-db",
                "ip": "10.0.0.1",
                "role": "database",
                "encryption_at_rest": True,
                "backup_enabled": True,
            }
        ]
        json_file = tmp_path / "secure.json"
        json_file.write_text(json.dumps(data))

        scanner = OnPremScanner.from_cmdb_json(json_file)
        result = scanner.scan()

        assert result.components_found == 1
        comp = next(iter(result.graph.components.values()))
        assert comp.security is not None
        assert comp.security.encryption_at_rest is True
        assert comp.security.backup_enabled is True


# ===========================================================================
# OnPremScanner — nmap XML
# ===========================================================================

class TestOnPremScannerNmapXML:
    """OnPremScanner can parse an nmap XML file to produce an InfraGraph."""

    def test_nmap_creates_expected_component_count(self, tmp_path):
        from faultray.discovery.onprem_scanner import OnPremScanner

        xml_file = tmp_path / "scan.xml"
        xml_file.write_text(SAMPLE_NMAP_XML)

        scanner = OnPremScanner.from_nmap_xml(xml_file)
        result = scanner.scan()

        assert result.components_found == 2

    def test_nmap_infers_web_server_from_port_80_443(self, tmp_path):
        from faultray.discovery.onprem_scanner import OnPremScanner

        xml_file = tmp_path / "scan.xml"
        xml_file.write_text(SAMPLE_NMAP_XML)

        scanner = OnPremScanner.from_nmap_xml(xml_file)
        result = scanner.scan()

        types = {comp.type for comp in result.graph.components.values()}
        # Host with ports 80/443 should become WEB_SERVER
        assert ComponentType.WEB_SERVER in types

    def test_nmap_infers_database_from_port_3306(self, tmp_path):
        from faultray.discovery.onprem_scanner import OnPremScanner

        xml_file = tmp_path / "scan.xml"
        xml_file.write_text(SAMPLE_NMAP_XML)

        scanner = OnPremScanner.from_nmap_xml(xml_file)
        result = scanner.scan()

        types = {comp.type for comp in result.graph.components.values()}
        assert ComponentType.DATABASE in types

    def test_nmap_hosts_have_correct_ips(self, tmp_path):
        from faultray.discovery.onprem_scanner import OnPremScanner

        xml_file = tmp_path / "scan.xml"
        xml_file.write_text(SAMPLE_NMAP_XML)

        scanner = OnPremScanner.from_nmap_xml(xml_file)
        result = scanner.scan()

        hosts = {comp.host for comp in result.graph.components.values()}
        assert "10.0.1.10" in hosts
        assert "10.0.1.20" in hosts

    def test_nmap_returns_onprem_discovery_result_type(self, tmp_path):
        from faultray.discovery.onprem_scanner import OnPremDiscoveryResult, OnPremScanner

        xml_file = tmp_path / "scan.xml"
        xml_file.write_text(SAMPLE_NMAP_XML)

        scanner = OnPremScanner.from_nmap_xml(xml_file)
        result = scanner.scan()

        assert isinstance(result, OnPremDiscoveryResult)
        assert isinstance(result.graph, InfraGraph)

    def test_nmap_missing_file_produces_warning(self, tmp_path):
        from faultray.discovery.onprem_scanner import OnPremScanner

        scanner = OnPremScanner.from_nmap_xml(tmp_path / "no_such.xml")
        result = scanner.scan()

        assert result.components_found == 0
        assert len(result.warnings) > 0

    def test_nmap_skips_down_hosts(self, tmp_path):
        """Hosts with state != 'up' are ignored."""
        from faultray.discovery.onprem_scanner import OnPremScanner

        xml = textwrap.dedent("""\
            <?xml version="1.0"?>
            <nmaprun>
              <host>
                <status state="down"/>
                <address addr="10.0.1.99" addrtype="ipv4"/>
                <ports>
                  <port portid="80"><state state="open"/><service name="http"/></port>
                </ports>
              </host>
            </nmaprun>
        """)
        xml_file = tmp_path / "down.xml"
        xml_file.write_text(xml)

        scanner = OnPremScanner.from_nmap_xml(xml_file)
        result = scanner.scan()

        assert result.components_found == 0

    def test_nmap_only_counts_open_ports(self, tmp_path):
        """Only ports with state='open' contribute to component type inference."""
        from faultray.discovery.onprem_scanner import OnPremScanner

        xml = textwrap.dedent("""\
            <?xml version="1.0"?>
            <nmaprun>
              <host>
                <status state="up"/>
                <address addr="10.0.0.5" addrtype="ipv4"/>
                <ports>
                  <port portid="3306"><state state="closed"/><service name="mysql"/></port>
                  <port portid="22"><state state="open"/><service name="ssh"/></port>
                </ports>
              </host>
            </nmaprun>
        """)
        xml_file = tmp_path / "mixed.xml"
        xml_file.write_text(xml)

        scanner = OnPremScanner.from_nmap_xml(xml_file)
        result = scanner.scan()

        # Only the SSH port is open, so 1 component added as APP_SERVER
        assert result.components_found == 1
        comp = next(iter(result.graph.components.values()))
        assert comp.type == ComponentType.APP_SERVER

    def test_nmap_infers_postgresql_from_port_5432(self, tmp_path):
        from faultray.discovery.onprem_scanner import OnPremScanner

        xml = textwrap.dedent("""\
            <?xml version="1.0"?>
            <nmaprun>
              <host>
                <status state="up"/>
                <address addr="10.0.0.10" addrtype="ipv4"/>
                <ports>
                  <port portid="5432"><state state="open"/><service name="postgresql"/></port>
                </ports>
              </host>
            </nmaprun>
        """)
        xml_file = tmp_path / "pg.xml"
        xml_file.write_text(xml)

        scanner = OnPremScanner.from_nmap_xml(xml_file)
        result = scanner.scan()

        assert result.components_found == 1
        comp = next(iter(result.graph.components.values()))
        assert comp.type == ComponentType.DATABASE

    def test_nmap_tags_include_open_ports(self, tmp_path):
        """Component tags include 'port:NNN' entries for open ports."""
        from faultray.discovery.onprem_scanner import OnPremScanner

        xml_file = tmp_path / "scan.xml"
        xml_file.write_text(SAMPLE_NMAP_XML)

        scanner = OnPremScanner.from_nmap_xml(xml_file)
        result = scanner.scan()

        all_tags = [tag for comp in result.graph.components.values() for tag in comp.tags]
        assert any(tag.startswith("port:") for tag in all_tags)
        assert "nmap_discovered" in all_tags


# ===========================================================================
# OnPremScanner — type inference helpers
# ===========================================================================

class TestOnPremTypeInference:
    """_normalize_component_type and _infer_type_from_ports work correctly."""

    def test_normalize_db_aliases(self):
        from faultray.discovery.onprem_scanner import _normalize_component_type

        for alias in ("db", "database", "mysql", "postgres", "postgresql", "oracle", "mongodb"):
            result = _normalize_component_type(alias)
            assert result == ComponentType.DATABASE, f"Alias '{alias}' should map to DATABASE"

    def test_normalize_web_server_aliases(self):
        from faultray.discovery.onprem_scanner import _normalize_component_type

        for alias in ("web", "web_server", "webserver", "nginx", "apache"):
            result = _normalize_component_type(alias)
            assert result == ComponentType.WEB_SERVER, f"Alias '{alias}' should map to WEB_SERVER"

    def test_normalize_cache_aliases(self):
        from faultray.discovery.onprem_scanner import _normalize_component_type

        for alias in ("cache", "redis", "memcached"):
            result = _normalize_component_type(alias)
            assert result == ComponentType.CACHE, f"Alias '{alias}' should map to CACHE"

    def test_normalize_unknown_defaults_to_app_server(self):
        from faultray.discovery.onprem_scanner import _normalize_component_type

        result = _normalize_component_type("something_unknown")
        assert result == ComponentType.APP_SERVER

    def test_infer_type_database_wins_over_web(self):
        """DB port has higher priority than web port."""
        from faultray.discovery.onprem_scanner import OnPremScanner

        scanner = OnPremScanner.from_nmap_xml("/dev/null")  # source path unused
        ct, svc = scanner._infer_type_from_ports([(80, "http"), (3306, "mysql")])
        assert ct == ComponentType.DATABASE

    def test_infer_type_cache_wins_over_web(self):
        """Cache port has higher priority than web port."""
        from faultray.discovery.onprem_scanner import OnPremScanner

        scanner = OnPremScanner.from_nmap_xml("/dev/null")
        ct, svc = scanner._infer_type_from_ports([(443, "https"), (6379, "redis")])
        assert ct == ComponentType.CACHE

    def test_infer_type_fallback_for_unknown_port(self):
        from faultray.discovery.onprem_scanner import OnPremScanner

        scanner = OnPremScanner.from_nmap_xml("/dev/null")
        ct, svc = scanner._infer_type_from_ports([(12345, "unknown-svc")])
        assert ct == ComponentType.APP_SERVER
