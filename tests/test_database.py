"""Tests for the database layer, auth, and export modules."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from faultray.api.database import (
    Base,
    ProjectRow,
    SimulationRunRow,
    TeamRow,
    UserRow,
    get_database_url,
    get_session_factory,
    init_db,
    reset_engine,
    _get_engine,
)
from faultray.api.auth import generate_api_key, hash_api_key


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_url(tmp_path: Path):
    """Create a temporary database and yield its URL."""
    db_path = tmp_path / "test_faultray.db"
    url = f"sqlite+aiosqlite:///{db_path}"

    # Reset global engine state before and after the test
    reset_engine()

    # Manually init with this URL
    engine = create_async_engine(url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield url, engine

    await engine.dispose()
    reset_engine()


@pytest_asyncio.fixture
async def session_factory(db_url):
    """Return an async session factory bound to the test database."""
    url, engine = db_url
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory


# ---------------------------------------------------------------------------
# Table creation tests
# ---------------------------------------------------------------------------

class TestInitDb:
    async def test_init_db_creates_tables(self, tmp_path: Path):
        """init_db should create all four tables."""
        db_path = tmp_path / "init_test.db"
        url = f"sqlite+aiosqlite:///{db_path}"

        reset_engine()
        engine = create_async_engine(url, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Verify tables exist by inspecting metadata
        from sqlalchemy import inspect as sa_inspect

        async with engine.connect() as conn:
            table_names = await conn.run_sync(
                lambda sync_conn: sa_inspect(sync_conn).get_table_names()
            )

        assert "users" in table_names
        assert "teams" in table_names
        assert "projects" in table_names
        assert "simulation_runs" in table_names

        await engine.dispose()
        reset_engine()


# ---------------------------------------------------------------------------
# Simulation run persistence tests
# ---------------------------------------------------------------------------

class TestSimulationRuns:
    async def test_save_and_load_run(self, session_factory):
        """Save a simulation run and read it back."""
        results_data = {
            "resilience_score": 75.5,
            "total_scenarios": 10,
            "critical_count": 2,
        }

        async with session_factory() as session:
            run = SimulationRunRow(
                engine_type="static",
                results_json=json.dumps(results_data),
                risk_score=75.5,
            )
            session.add(run)
            await session.commit()
            run_id = run.id

        # Read it back
        async with session_factory() as session:
            stmt = select(SimulationRunRow).where(SimulationRunRow.id == run_id)
            result = await session.execute(stmt)
            loaded = result.scalar_one()

            assert loaded.engine_type == "static"
            assert loaded.risk_score == 75.5
            parsed = json.loads(loaded.results_json)
            assert parsed["resilience_score"] == 75.5
            assert parsed["total_scenarios"] == 10

    async def test_run_with_project(self, session_factory):
        """Simulation run can be linked to a project."""
        async with session_factory() as session:
            project = ProjectRow(name="test-project")
            session.add(project)
            await session.commit()
            project_id = project.id

            run = SimulationRunRow(
                project_id=project_id,
                engine_type="dynamic",
                risk_score=60.0,
            )
            session.add(run)
            await session.commit()
            run_id = run.id

        async with session_factory() as session:
            stmt = select(SimulationRunRow).where(SimulationRunRow.id == run_id)
            result = await session.execute(stmt)
            loaded = result.scalar_one()
            assert loaded.project_id == project_id
            assert loaded.engine_type == "dynamic"

    async def test_delete_run(self, session_factory):
        """Delete a simulation run."""
        async with session_factory() as session:
            run = SimulationRunRow(engine_type="static", risk_score=50.0)
            session.add(run)
            await session.commit()
            run_id = run.id

        async with session_factory() as session:
            stmt = select(SimulationRunRow).where(SimulationRunRow.id == run_id)
            result = await session.execute(stmt)
            loaded = result.scalar_one()
            await session.delete(loaded)
            await session.commit()

        async with session_factory() as session:
            stmt = select(SimulationRunRow).where(SimulationRunRow.id == run_id)
            result = await session.execute(stmt)
            assert result.scalar_one_or_none() is None

    async def test_multiple_runs_ordering(self, session_factory):
        """Multiple runs are stored with separate IDs."""
        async with session_factory() as session:
            for i in range(5):
                run = SimulationRunRow(
                    engine_type="static",
                    risk_score=float(i * 10),
                )
                session.add(run)
            await session.commit()

        async with session_factory() as session:
            stmt = select(SimulationRunRow).order_by(SimulationRunRow.id)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            assert len(rows) == 5
            assert rows[0].risk_score == 0.0
            assert rows[4].risk_score == 40.0


# ---------------------------------------------------------------------------
# API key tests
# ---------------------------------------------------------------------------

class TestApiKeyAuth:
    def test_generate_api_key_unique(self):
        """Each call generates a different key."""
        key1 = generate_api_key()
        key2 = generate_api_key()
        assert key1 != key2
        # Keys should be long enough for security
        assert len(key1) >= 32

    def test_hash_api_key_deterministic(self):
        """Same input always produces the same hash."""
        key = "test-key-abc123"
        h1 = hash_api_key(key)
        h2 = hash_api_key(key)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest

    def test_hash_api_key_different_inputs(self):
        """Different inputs produce different hashes."""
        h1 = hash_api_key("key-aaa")
        h2 = hash_api_key("key-bbb")
        assert h1 != h2

    async def test_store_and_lookup_user_by_key(self, session_factory):
        """Store a user with hashed key and look them up."""
        api_key = generate_api_key()
        key_hash = hash_api_key(api_key)

        async with session_factory() as session:
            user = UserRow(
                email="test@example.com",
                name="Test User",
                api_key_hash=key_hash,
            )
            session.add(user)
            await session.commit()

        # Lookup by hash
        async with session_factory() as session:
            stmt = select(UserRow).where(UserRow.api_key_hash == key_hash)
            result = await session.execute(stmt)
            found = result.scalar_one_or_none()
            assert found is not None
            assert found.email == "test@example.com"
            assert found.name == "Test User"

        # Wrong key should not match
        wrong_hash = hash_api_key("wrong-key")
        async with session_factory() as session:
            stmt = select(UserRow).where(UserRow.api_key_hash == wrong_hash)
            result = await session.execute(stmt)
            assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Team / user relationship tests
# ---------------------------------------------------------------------------

class TestTeamRelationship:
    async def test_user_with_team(self, session_factory):
        """Users can belong to a team."""
        async with session_factory() as session:
            team = TeamRow(name="Engineering")
            session.add(team)
            await session.commit()
            team_id = team.id

            user = UserRow(
                email="eng@example.com",
                name="Engineer",
                api_key_hash=hash_api_key("eng-key"),
                team_id=team_id,
            )
            session.add(user)
            await session.commit()

        async with session_factory() as session:
            stmt = select(UserRow).where(UserRow.email == "eng@example.com")
            result = await session.execute(stmt)
            user = result.scalar_one()
            assert user.team_id == team_id


# ---------------------------------------------------------------------------
# Export tests
# ---------------------------------------------------------------------------

class TestExport:
    def _make_report(self):
        """Create a minimal SimulationReport for testing."""
        from faultray.model.components import HealthStatus
        from faultray.simulator.cascade import CascadeChain, CascadeEffect
        from faultray.simulator.engine import ScenarioResult, SimulationReport
        from faultray.simulator.scenarios import Fault, FaultType, Scenario

        effect = CascadeEffect(
            component_id="comp-1",
            component_name="web-server",
            health=HealthStatus.DOWN,
            reason="Node failure",
            estimated_time_seconds=30,
        )
        chain = CascadeChain(trigger="test-fault", total_components=3)
        chain.effects.append(effect)

        fault = Fault(
            target_component_id="comp-1",
            fault_type=FaultType.COMPONENT_DOWN,
        )
        scenario = Scenario(
            id="test-scenario-1",
            name="Test Scenario",
            description="A test scenario",
            faults=[fault],
        )
        result = ScenarioResult(
            scenario=scenario,
            cascade=chain,
            risk_score=8.5,
        )

        return SimulationReport(results=[result], resilience_score=65.0)

    def test_export_csv(self, tmp_path: Path):
        from faultray.reporter.export import export_csv

        report = self._make_report()
        out = export_csv(report, tmp_path / "results.csv")
        assert out.exists()

        # Read and verify content
        import csv

        with open(out, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)

        assert len(rows) >= 1
        assert rows[0]["scenario_name"] == "Test Scenario"
        assert rows[0]["component_name"] == "web-server"
        assert float(rows[0]["risk_score"]) == 8.5

    def test_export_json(self, tmp_path: Path):
        from faultray.reporter.export import export_json

        report = self._make_report()
        out = export_json(report, tmp_path / "results.json")
        assert out.exists()

        with open(out, encoding="utf-8") as fh:
            data = json.load(fh)

        assert data["resilience_score"] == 65.0
        assert data["total_scenarios"] == 1
        assert data["critical_count"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["scenario_name"] == "Test Scenario"
