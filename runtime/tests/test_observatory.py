"""
Observatory Tests - Phase I Read-Only Enforcement Audit.

CONSTITUTIONAL CONSTRAINT: All tests verify read-only behavior.
"""
import pytest
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta

from runtime.logging.pg_pool import get_conn, put_conn, init_pool
from runtime.observatory.repository import ObservatoryRepository
from runtime.observatory.schemas import (
    StabilityStatusEnum, MandateType, Direction,
    StabilityResponse, HealthResponse, ObservatorySnapshot
)

# Ensure PG pool is initialized before any DB access
init_pool()


class TestReadOnlyEnforcement:
    """Verify read-only constraints are enforced."""

    def test_repository_reads_from_pg(self):
        """Repository can read from PG pool."""
        repo = ObservatoryRepository()

        # _safe_query should work for existing or non-existing tables
        # (returns empty list for missing tables)
        results = repo._safe_query("SELECT 1 AS id")
        assert len(results) == 1
        assert results[0]['id'] == 1

    def test_repository_has_no_write_methods(self):
        """Repository exposes only read (SELECT) methods - no INSERT/UPDATE/DELETE."""
        repo = ObservatoryRepository()
        # Verify the public API is read-only by checking method names
        public_methods = [m for m in dir(repo) if not m.startswith('_')]
        write_keywords = ['insert', 'update', 'delete', 'create', 'drop', 'save', 'write']
        for method in public_methods:
            for kw in write_keywords:
                assert kw not in method.lower(), \
                    f"Repository has write-like method: {method}"

    def test_safe_query_handles_missing_table(self):
        """_safe_query returns empty list for missing tables."""
        repo = ObservatoryRepository()
        results = repo._safe_query("SELECT * FROM nonexistent_table_xyz_test")
        assert results == []

    def test_safe_query_handles_missing_column(self):
        """_safe_query returns empty list for missing columns."""
        repo = ObservatoryRepository()
        # Query a table that likely exists but with a non-existent column
        # _safe_query should catch the PG error and return []
        results = repo._safe_query(
            "SELECT nonexistent_col_xyz FROM positions"
        )
        assert results == []


class TestSchemaImmutability:
    """Verify schema types are properly defined."""

    def test_stability_status_enum_values(self):
        """StabilityStatusEnum has correct values."""
        assert StabilityStatusEnum.STABLE.value == "STABLE"
        assert StabilityStatusEnum.WARNING.value == "WARNING"
        assert StabilityStatusEnum.CRITICAL.value == "CRITICAL"
        assert StabilityStatusEnum.UNKNOWN.value == "UNKNOWN"

    def test_mandate_type_enum_values(self):
        """MandateType has correct values."""
        assert MandateType.ENTRY.value == "ENTRY"
        assert MandateType.EXIT.value == "EXIT"
        assert MandateType.BLOCK.value == "BLOCK"

    def test_direction_enum_values(self):
        """Direction has correct values."""
        assert Direction.LONG.value == "LONG"
        assert Direction.SHORT.value == "SHORT"

    def test_stability_response_defaults(self):
        """StabilityResponse has proper defaults."""
        resp = StabilityResponse(status=StabilityStatusEnum.UNKNOWN)
        assert resp.total_mandates == 0
        assert resp.total_actions == 0
        assert resp.issues_total == 0
        assert resp.recent_issues == []

    def test_health_response_defaults(self):
        """HealthResponse has proper defaults."""
        resp = HealthResponse()
        assert resp.status == "UNKNOWN"
        assert resp.memory_mb == 0.0
        assert resp.cycles_completed == 0


class TestServerEndpoints:
    """Verify server has only GET endpoints."""

    def test_no_post_endpoints(self):
        """Server has no POST endpoints."""
        from runtime.observatory.server import app

        for route in app.routes:
            if hasattr(route, 'methods'):
                assert 'POST' not in route.methods, f"Found POST on {route.path}"

    def test_no_put_endpoints(self):
        """Server has no PUT endpoints."""
        from runtime.observatory.server import app

        for route in app.routes:
            if hasattr(route, 'methods'):
                assert 'PUT' not in route.methods, f"Found PUT on {route.path}"

    def test_no_delete_endpoints(self):
        """Server has no DELETE endpoints."""
        from runtime.observatory.server import app

        for route in app.routes:
            if hasattr(route, 'methods'):
                assert 'DELETE' not in route.methods, f"Found DELETE on {route.path}"

    def test_cors_get_only(self):
        """CORS middleware allows only GET."""
        from runtime.observatory.server import app

        for middleware in app.user_middleware:
            if middleware.cls.__name__ == 'CORSMiddleware':
                # Check the options passed to CORS
                options = middleware.options
                assert options.get('allow_methods') == ['GET'], \
                    f"CORS allows methods other than GET: {options.get('allow_methods')}"


class TestAPIResponses:
    """Verify API endpoints return valid responses."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from fastapi.testclient import TestClient
        from runtime.observatory.server import app
        return TestClient(app)

    def test_root_endpoint(self, client):
        """Root endpoint returns API info."""
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data['name'] == "Liquidation Trading Observatory"
        assert data['version'] == "1.0.0"

    def test_health_endpoint(self, client):
        """Health endpoint returns valid response."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert 'status' in data
        assert 'memory_mb' in data
        assert 'uptime_seconds' in data

    def test_stability_endpoint(self, client):
        """Stability endpoint returns valid response."""
        resp = client.get("/api/stability")
        assert resp.status_code == 200
        data = resp.json()
        assert 'status' in data
        assert data['status'] in ['STABLE', 'WARNING', 'CRITICAL', 'UNKNOWN']

    def test_snapshot_endpoint(self, client):
        """Snapshot endpoint returns aggregated data."""
        resp = client.get("/api/snapshot")
        assert resp.status_code == 200
        data = resp.json()
        assert 'timestamp' in data
        assert 'stability' in data
        assert 'health' in data

    def test_cycles_endpoint(self, client):
        """Cycles endpoint returns list."""
        resp = client.get("/api/cycles")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_mandates_endpoint(self, client):
        """Mandates endpoint returns list."""
        resp = client.get("/api/mandates")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_zones_endpoint(self, client):
        """Zones endpoint returns list."""
        resp = client.get("/api/zones")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_liquidations_endpoint(self, client):
        """Liquidations endpoint returns list."""
        resp = client.get("/api/liquidations")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
