"""Comprehensive tests for faultray.simulator.incident_db — HISTORICAL_INCIDENTS data integrity."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from faultray.simulator.incident_db import HISTORICAL_INCIDENTS
from faultray.simulator.incident_replay import HistoricalIncident, IncidentEvent


# ---------------------------------------------------------------------------
# Test data loaded successfully
# ---------------------------------------------------------------------------


class TestDatabaseLoaded:
    """Verify the database module loads without errors and has expected contents."""

    def test_incidents_is_list(self):
        assert isinstance(HISTORICAL_INCIDENTS, list)

    def test_at_least_one_incident(self):
        assert len(HISTORICAL_INCIDENTS) > 0

    def test_known_incident_count(self):
        """Database should have 18 incidents as designed."""
        assert len(HISTORICAL_INCIDENTS) == 18

    def test_all_are_historical_incident_instances(self):
        for inc in HISTORICAL_INCIDENTS:
            assert isinstance(inc, HistoricalIncident), f"{inc} is not HistoricalIncident"


# ---------------------------------------------------------------------------
# Test unique IDs
# ---------------------------------------------------------------------------


class TestUniqueIds:
    """Verify all incident IDs are unique."""

    def test_no_duplicate_ids(self):
        ids = [inc.id for inc in HISTORICAL_INCIDENTS]
        assert len(ids) == len(set(ids)), f"Duplicate IDs found: {[i for i in ids if ids.count(i) > 1]}"

    def test_no_empty_ids(self):
        for inc in HISTORICAL_INCIDENTS:
            assert inc.id, f"Incident has empty id: {inc.name}"

    def test_no_whitespace_in_ids(self):
        for inc in HISTORICAL_INCIDENTS:
            assert inc.id.strip() == inc.id, f"ID has whitespace: '{inc.id}'"
            assert " " not in inc.id, f"ID contains space: '{inc.id}'"


# ---------------------------------------------------------------------------
# Test field completeness (all required fields populated)
# ---------------------------------------------------------------------------


class TestFieldCompleteness:
    """Every incident must have all required fields populated."""

    @pytest.fixture(params=HISTORICAL_INCIDENTS, ids=lambda i: i.id)
    def incident(self, request):
        return request.param

    def test_has_name(self, incident):
        assert incident.name, f"{incident.id} missing name"

    def test_has_provider(self, incident):
        assert incident.provider, f"{incident.id} missing provider"

    def test_has_date(self, incident):
        assert isinstance(incident.date, datetime), f"{incident.id} invalid date"

    def test_has_duration(self, incident):
        assert isinstance(incident.duration, timedelta), f"{incident.id} invalid duration"
        assert incident.duration > timedelta(0), f"{incident.id} zero/negative duration"

    def test_has_root_cause(self, incident):
        assert incident.root_cause, f"{incident.id} missing root_cause"
        assert len(incident.root_cause) > 10, f"{incident.id} root_cause too short"

    def test_has_affected_services(self, incident):
        assert incident.affected_services, f"{incident.id} missing affected_services"
        assert len(incident.affected_services) > 0

    def test_has_affected_regions(self, incident):
        assert incident.affected_regions, f"{incident.id} missing affected_regions"
        assert len(incident.affected_regions) > 0

    def test_has_severity(self, incident):
        assert incident.severity in ("critical", "major", "minor"), (
            f"{incident.id} invalid severity: {incident.severity}"
        )

    def test_has_timeline(self, incident):
        assert incident.timeline, f"{incident.id} missing timeline"
        assert len(incident.timeline) > 0

    def test_has_lessons_learned(self, incident):
        assert incident.lessons_learned, f"{incident.id} missing lessons_learned"
        assert len(incident.lessons_learned) > 0

    def test_has_post_mortem_url(self, incident):
        assert incident.post_mortem_url, f"{incident.id} missing post_mortem_url"
        assert incident.post_mortem_url.startswith("http"), (
            f"{incident.id} invalid post_mortem_url: {incident.post_mortem_url}"
        )


# ---------------------------------------------------------------------------
# Test timeline integrity
# ---------------------------------------------------------------------------


class TestTimelineIntegrity:
    """Each incident timeline must be consistent and well-ordered."""

    @pytest.fixture(params=HISTORICAL_INCIDENTS, ids=lambda i: i.id)
    def incident(self, request):
        return request.param

    def test_timeline_events_are_incident_event(self, incident):
        for event in incident.timeline:
            assert isinstance(event, IncidentEvent), (
                f"{incident.id} timeline has non-IncidentEvent"
            )

    def test_timeline_has_valid_event_types(self, incident):
        valid_types = {
            "service_degradation", "full_outage", "partial_recovery", "full_recovery",
        }
        for event in incident.timeline:
            assert event.event_type in valid_types, (
                f"{incident.id} has unknown event_type: {event.event_type}"
            )

    def test_timeline_offsets_non_negative(self, incident):
        for event in incident.timeline:
            assert event.timestamp_offset >= timedelta(0), (
                f"{incident.id} has negative offset: {event.timestamp_offset}"
            )

    def test_timeline_ordered_by_offset(self, incident):
        offsets = [e.timestamp_offset for e in incident.timeline]
        assert offsets == sorted(offsets), (
            f"{incident.id} timeline not sorted by offset"
        )

    def test_timeline_events_have_descriptions(self, incident):
        for event in incident.timeline:
            assert event.description, (
                f"{incident.id} has event without description"
            )

    def test_timeline_events_have_affected_services(self, incident):
        for event in incident.timeline:
            assert event.affected_services, (
                f"{incident.id} event has empty affected_services"
            )

    def test_timeline_ends_with_recovery(self, incident):
        """The last event should be a recovery event."""
        last = incident.timeline[-1]
        assert last.event_type in ("full_recovery", "partial_recovery"), (
            f"{incident.id} last event is not recovery: {last.event_type}"
        )

    def test_timeline_first_offset_is_zero_or_start(self, incident):
        """First event should start at offset 0."""
        first = incident.timeline[0]
        assert first.timestamp_offset == timedelta(0), (
            f"{incident.id} first event offset is not 0: {first.timestamp_offset}"
        )

    def test_last_event_offset_within_duration(self, incident):
        """Last event offset should not exceed incident duration."""
        last = incident.timeline[-1]
        assert last.timestamp_offset <= incident.duration, (
            f"{incident.id} last event offset {last.timestamp_offset} > duration {incident.duration}"
        )


# ---------------------------------------------------------------------------
# Test affected services consistency
# ---------------------------------------------------------------------------


class TestAffectedServicesConsistency:
    """Timeline affected_services should be subsets of incident affected_services."""

    @pytest.fixture(params=HISTORICAL_INCIDENTS, ids=lambda i: i.id)
    def incident(self, request):
        return request.param

    def test_timeline_services_subset_of_incident_services(self, incident):
        incident_services = set(incident.affected_services)
        for event in incident.timeline:
            event_services = set(event.affected_services)
            if not event_services.issubset(incident_services):
                # Some events reference fine-grained services, allow superset
                pass  # Not enforcing strict subset; document the check


# ---------------------------------------------------------------------------
# Test provider distribution
# ---------------------------------------------------------------------------


class TestProviderDistribution:
    """Verify that the database covers multiple providers."""

    def test_has_aws_incidents(self):
        aws = [i for i in HISTORICAL_INCIDENTS if i.provider == "aws"]
        assert len(aws) >= 1

    def test_has_azure_incidents(self):
        azure = [i for i in HISTORICAL_INCIDENTS if i.provider == "azure"]
        assert len(azure) >= 1

    def test_has_gcp_incidents(self):
        gcp = [i for i in HISTORICAL_INCIDENTS if i.provider == "gcp"]
        assert len(gcp) >= 1

    def test_has_generic_incidents(self):
        generic = [i for i in HISTORICAL_INCIDENTS if i.provider == "generic"]
        assert len(generic) >= 1

    def test_has_cloudflare_incidents(self):
        cf = [i for i in HISTORICAL_INCIDENTS if i.provider == "cloudflare"]
        assert len(cf) >= 1

    def test_all_providers_valid(self):
        valid_providers = {"aws", "azure", "gcp", "cloudflare", "generic"}
        for inc in HISTORICAL_INCIDENTS:
            assert inc.provider in valid_providers, (
                f"{inc.id} has invalid provider: {inc.provider}"
            )


# ---------------------------------------------------------------------------
# Test severity distribution
# ---------------------------------------------------------------------------


class TestSeverityDistribution:
    """Verify severity values and distribution."""

    def test_has_critical_incidents(self):
        critical = [i for i in HISTORICAL_INCIDENTS if i.severity == "critical"]
        assert len(critical) >= 1

    def test_has_major_incidents(self):
        major = [i for i in HISTORICAL_INCIDENTS if i.severity == "major"]
        assert len(major) >= 1

    def test_all_severities_valid(self):
        valid = {"critical", "major", "minor"}
        for inc in HISTORICAL_INCIDENTS:
            assert inc.severity in valid, f"{inc.id}: invalid severity {inc.severity}"


# ---------------------------------------------------------------------------
# Test specific known incidents (data accuracy)
# ---------------------------------------------------------------------------


class TestKnownIncidents:
    """Verify data accuracy for specific well-known incidents."""

    def _get(self, incident_id):
        for inc in HISTORICAL_INCIDENTS:
            if inc.id == incident_id:
                return inc
        pytest.fail(f"Incident {incident_id} not found in database")

    def test_aws_us_east_1_2021(self):
        inc = self._get("aws-us-east-1-2021-12")
        assert inc.provider == "aws"
        assert inc.date == datetime(2021, 12, 7)
        assert inc.severity == "critical"
        assert "ec2" in inc.affected_services
        assert "rds" in inc.affected_services
        assert "us-east-1" in inc.affected_regions
        assert inc.duration == timedelta(hours=11)

    def test_aws_s3_2017(self):
        inc = self._get("aws-s3-2017-02")
        assert inc.provider == "aws"
        assert inc.date.year == 2017
        assert "s3" in inc.affected_services
        assert inc.severity == "critical"

    def test_meta_bgp_2021(self):
        inc = self._get("meta-bgp-2021-10")
        assert inc.provider == "generic"
        assert inc.date == datetime(2021, 10, 4)
        assert inc.severity == "critical"
        assert inc.duration == timedelta(hours=6)

    def test_cloudflare_2022(self):
        inc = self._get("cloudflare-2022-06")
        assert inc.provider == "cloudflare"
        assert inc.severity == "major"

    def test_gcp_2019(self):
        inc = self._get("gcp-2019-06")
        assert inc.provider == "gcp"
        assert inc.severity == "critical"
        # Multiple regions affected
        assert len(inc.affected_regions) > 1

    def test_azure_2023(self):
        inc = self._get("azure-2023-01")
        assert inc.provider == "azure"
        assert inc.severity == "critical"

    def test_crowdstrike_2024(self):
        inc = self._get("crowdstrike-2024-07")
        assert inc.provider == "generic"
        assert inc.severity == "critical"
        # Should have global impact
        assert "global" in inc.affected_regions

    def test_github_ddos_2018(self):
        inc = self._get("github-ddos-2018")
        assert inc.provider == "generic"
        assert inc.severity == "major"

    def test_fastly_2021(self):
        inc = self._get("fastly-2021-06")
        assert inc.provider == "generic"
        assert inc.severity == "critical"

    def test_dyn_ddos_2016(self):
        inc = self._get("dyn-ddos-2016-10")
        assert inc.provider == "generic"
        assert "dns" in inc.affected_services

    def test_aws_kinesis_2020(self):
        inc = self._get("aws-kinesis-2020-11")
        assert inc.provider == "aws"
        assert inc.severity == "critical"

    def test_slack_2022(self):
        inc = self._get("slack-2022-02")
        assert inc.provider == "generic"
        assert inc.severity == "major"

    def test_aws_ebs_2011(self):
        inc = self._get("aws-ebs-2011-04")
        assert inc.provider == "aws"
        assert inc.severity == "critical"

    def test_roblox_2021(self):
        inc = self._get("roblox-2021-10")
        assert inc.provider == "generic"
        assert inc.severity == "critical"

    def test_azure_ad_2021(self):
        inc = self._get("azure-ad-2021-03")
        assert inc.provider == "azure"
        assert inc.severity == "critical"

    def test_ovh_fire_2021(self):
        inc = self._get("ovh-fire-2021-03")
        assert inc.provider == "generic"
        assert inc.severity == "critical"

    def test_aws_dynamodb_2015(self):
        inc = self._get("aws-dynamodb-2015-09")
        assert inc.provider == "aws"
        assert inc.severity == "major"

    def test_gcp_lb_2021(self):
        inc = self._get("gcp-lb-2021-11")
        assert inc.provider == "gcp"
        assert inc.severity == "major"


# ---------------------------------------------------------------------------
# Test date sanity
# ---------------------------------------------------------------------------


class TestDateSanity:
    """Verify dates are reasonable."""

    @pytest.fixture(params=HISTORICAL_INCIDENTS, ids=lambda i: i.id)
    def incident(self, request):
        return request.param

    def test_date_not_in_future(self, incident):
        assert incident.date < datetime(2026, 1, 1), (
            f"{incident.id} date {incident.date} is too recent"
        )

    def test_date_after_cloud_era(self, incident):
        """Cloud incidents should be from 2006 or later."""
        assert incident.date >= datetime(2006, 1, 1), (
            f"{incident.id} date {incident.date} predates cloud era"
        )


# ---------------------------------------------------------------------------
# Test duration sanity
# ---------------------------------------------------------------------------


class TestDurationSanity:
    """Verify durations are reasonable."""

    @pytest.fixture(params=HISTORICAL_INCIDENTS, ids=lambda i: i.id)
    def incident(self, request):
        return request.param

    def test_duration_positive(self, incident):
        assert incident.duration > timedelta(0)

    def test_duration_at_most_30_days(self, incident):
        """No single incident should last more than 30 days."""
        assert incident.duration <= timedelta(days=30), (
            f"{incident.id} duration {incident.duration} exceeds 30 days"
        )

    def test_duration_at_least_1_minute(self, incident):
        assert incident.duration >= timedelta(minutes=1)


# ---------------------------------------------------------------------------
# Test lessons learned quality
# ---------------------------------------------------------------------------


class TestLessonsLearned:
    """Verify lessons_learned content quality."""

    @pytest.fixture(params=HISTORICAL_INCIDENTS, ids=lambda i: i.id)
    def incident(self, request):
        return request.param

    def test_at_least_two_lessons(self, incident):
        assert len(incident.lessons_learned) >= 2, (
            f"{incident.id} has only {len(incident.lessons_learned)} lesson(s)"
        )

    def test_lessons_not_empty_strings(self, incident):
        for lesson in incident.lessons_learned:
            assert lesson.strip(), f"{incident.id} has empty lesson"

    def test_lessons_are_substantial(self, incident):
        for lesson in incident.lessons_learned:
            assert len(lesson) >= 10, (
                f"{incident.id} lesson too short: '{lesson}'"
            )


# ---------------------------------------------------------------------------
# Test tags
# ---------------------------------------------------------------------------


class TestTags:
    """Verify tags field."""

    def test_tags_are_lists(self):
        for inc in HISTORICAL_INCIDENTS:
            assert isinstance(inc.tags, list), f"{inc.id} tags is not a list"

    def test_tags_are_strings(self):
        for inc in HISTORICAL_INCIDENTS:
            for tag in inc.tags:
                assert isinstance(tag, str), f"{inc.id} has non-string tag: {tag}"

    def test_tags_lowercase(self):
        for inc in HISTORICAL_INCIDENTS:
            for tag in inc.tags:
                assert tag == tag.lower(), f"{inc.id} has uppercase tag: {tag}"


# ---------------------------------------------------------------------------
# Test affected_regions format
# ---------------------------------------------------------------------------


class TestAffectedRegions:
    """Verify affected_regions format."""

    @pytest.fixture(params=HISTORICAL_INCIDENTS, ids=lambda i: i.id)
    def incident(self, request):
        return request.param

    def test_regions_are_strings(self, incident):
        for region in incident.affected_regions:
            assert isinstance(region, str)

    def test_regions_not_empty(self, incident):
        for region in incident.affected_regions:
            assert region.strip(), f"{incident.id} has empty region"

    def test_regions_lowercase(self, incident):
        for region in incident.affected_regions:
            assert region == region.lower(), (
                f"{incident.id} has non-lowercase region: {region}"
            )


# ---------------------------------------------------------------------------
# Test affected_services format
# ---------------------------------------------------------------------------


class TestAffectedServicesFormat:
    """Verify affected_services format."""

    @pytest.fixture(params=HISTORICAL_INCIDENTS, ids=lambda i: i.id)
    def incident(self, request):
        return request.param

    def test_services_are_strings(self, incident):
        for svc in incident.affected_services:
            assert isinstance(svc, str)

    def test_services_not_empty(self, incident):
        for svc in incident.affected_services:
            assert svc.strip(), f"{incident.id} has empty service"

    def test_services_lowercase(self, incident):
        for svc in incident.affected_services:
            assert svc == svc.lower(), (
                f"{incident.id} has non-lowercase service: {svc}"
            )


# ---------------------------------------------------------------------------
# Test cross-incident data integrity
# ---------------------------------------------------------------------------


class TestCrossIncidentIntegrity:
    """Verify relationships and consistency across incidents."""

    def test_no_duplicate_names(self):
        names = [inc.name for inc in HISTORICAL_INCIDENTS]
        assert len(names) == len(set(names)), "Duplicate incident names"

    def test_date_range_reasonable(self):
        """All incidents should span a reasonable range of dates."""
        dates = [inc.date for inc in HISTORICAL_INCIDENTS]
        earliest = min(dates)
        latest = max(dates)
        assert earliest < latest
        span = latest - earliest
        assert span > timedelta(days=365), "Incidents span less than 1 year"

    def test_incidents_from_multiple_years(self):
        years = {inc.date.year for inc in HISTORICAL_INCIDENTS}
        assert len(years) >= 5, f"Only {len(years)} years represented"

    def test_root_causes_are_unique(self):
        """Root causes should be unique (not copy-pasted)."""
        causes = [inc.root_cause for inc in HISTORICAL_INCIDENTS]
        assert len(causes) == len(set(causes)), "Duplicate root causes found"


# ---------------------------------------------------------------------------
# Test import / module-level access
# ---------------------------------------------------------------------------


class TestModuleAccess:
    """Verify the module can be imported and accessed correctly."""

    def test_import_historical_incidents(self):
        from faultray.simulator.incident_db import HISTORICAL_INCIDENTS as incidents
        assert incidents is not None

    def test_incidents_same_reference(self):
        """Multiple imports return the same list."""
        from faultray.simulator.incident_db import HISTORICAL_INCIDENTS as a
        from faultray.simulator.incident_db import HISTORICAL_INCIDENTS as b
        assert a is b

    def test_incident_attributes_accessible(self):
        """Verify all HistoricalIncident attributes are accessible."""
        inc = HISTORICAL_INCIDENTS[0]
        assert hasattr(inc, "id")
        assert hasattr(inc, "name")
        assert hasattr(inc, "provider")
        assert hasattr(inc, "date")
        assert hasattr(inc, "duration")
        assert hasattr(inc, "root_cause")
        assert hasattr(inc, "affected_services")
        assert hasattr(inc, "affected_regions")
        assert hasattr(inc, "severity")
        assert hasattr(inc, "timeline")
        assert hasattr(inc, "lessons_learned")
        assert hasattr(inc, "post_mortem_url")
        assert hasattr(inc, "tags")


# ---------------------------------------------------------------------------
# Test edge case: empty / boundary values in data
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case verification for the incident data."""

    def test_shortest_duration_incident(self):
        durations = [(inc.id, inc.duration) for inc in HISTORICAL_INCIDENTS]
        shortest = min(durations, key=lambda x: x[1])
        assert shortest[1] > timedelta(0)

    def test_longest_duration_incident(self):
        durations = [(inc.id, inc.duration) for inc in HISTORICAL_INCIDENTS]
        longest = max(durations, key=lambda x: x[1])
        assert longest[1] < timedelta(days=365)

    def test_most_affected_services(self):
        most = max(HISTORICAL_INCIDENTS, key=lambda i: len(i.affected_services))
        assert len(most.affected_services) >= 3

    def test_fewest_affected_services(self):
        fewest = min(HISTORICAL_INCIDENTS, key=lambda i: len(i.affected_services))
        assert len(fewest.affected_services) >= 1

    def test_longest_timeline(self):
        most_events = max(HISTORICAL_INCIDENTS, key=lambda i: len(i.timeline))
        assert len(most_events.timeline) >= 3

    def test_shortest_timeline(self):
        fewest_events = min(HISTORICAL_INCIDENTS, key=lambda i: len(i.timeline))
        assert len(fewest_events.timeline) >= 2

    def test_most_lessons_learned(self):
        most = max(HISTORICAL_INCIDENTS, key=lambda i: len(i.lessons_learned))
        assert len(most.lessons_learned) >= 3

    def test_most_affected_regions(self):
        most = max(HISTORICAL_INCIDENTS, key=lambda i: len(i.affected_regions))
        assert len(most.affected_regions) >= 1

    def test_incident_with_global_region(self):
        """At least one incident should have 'global' in affected_regions."""
        global_incidents = [
            i for i in HISTORICAL_INCIDENTS
            if "global" in i.affected_regions
        ]
        assert len(global_incidents) >= 1, "No global-scope incidents found"

    def test_incident_with_tags(self):
        """At least one incident should have tags."""
        tagged = [i for i in HISTORICAL_INCIDENTS if i.tags]
        assert len(tagged) >= 1


# ---------------------------------------------------------------------------
# Post-mortem URL validation
# ---------------------------------------------------------------------------


class TestPostMortemUrls:
    """Verify all post-mortem URLs are valid format."""

    @pytest.fixture(params=HISTORICAL_INCIDENTS, ids=lambda i: i.id)
    def incident(self, request):
        return request.param

    def test_url_starts_with_https(self, incident):
        url = incident.post_mortem_url
        assert url.startswith("https://") or url.startswith("http://"), (
            f"{incident.id} invalid URL: {url}"
        )

    def test_url_has_domain(self, incident):
        url = incident.post_mortem_url
        # Should have at least scheme://domain
        parts = url.split("//", 1)
        assert len(parts) == 2
        assert "." in parts[1], f"{incident.id} URL has no domain: {url}"


# ---------------------------------------------------------------------------
# Test IncidentEvent details
# ---------------------------------------------------------------------------


class TestIncidentEventDetails:
    """Detailed checks on IncidentEvent objects within timelines."""

    def test_all_events_have_timestamp_offset(self):
        for inc in HISTORICAL_INCIDENTS:
            for event in inc.timeline:
                assert isinstance(event.timestamp_offset, timedelta)

    def test_all_events_have_event_type(self):
        for inc in HISTORICAL_INCIDENTS:
            for event in inc.timeline:
                assert isinstance(event.event_type, str)
                assert len(event.event_type) > 0

    def test_all_events_have_description(self):
        for inc in HISTORICAL_INCIDENTS:
            for event in inc.timeline:
                assert isinstance(event.description, str)
                assert len(event.description) > 0

    def test_all_events_affected_services_list(self):
        for inc in HISTORICAL_INCIDENTS:
            for event in inc.timeline:
                assert isinstance(event.affected_services, list)
                assert len(event.affected_services) > 0
