"""Tests for health and metrics endpoints."""

from __future__ import annotations


class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_health_when_opensearch_connected(self, client, mock_opensearch_client):
        """Health returns healthy when OpenSearch is reachable."""
        mock_opensearch_client.ping.return_value = True
        response = client.get("/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "healthy"
        assert data["dependencies"]["opensearch"] == "connected"

    def test_health_when_opensearch_disconnected(self, client, mock_opensearch_client):
        """Health returns 200 with degraded status when OpenSearch is unreachable."""
        mock_opensearch_client.ping.return_value = False
        response = client.get("/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "degraded"
        assert data["dependencies"]["opensearch"] == "disconnected"


class TestReadinessEndpoint:
    """Tests for GET /health/ready."""

    def test_ready_when_opensearch_connected(self, client, mock_opensearch_client):
        """Readiness returns 200 when OpenSearch is reachable."""
        mock_opensearch_client.ping.return_value = True
        response = client.get("/health/ready")
        assert response.status_code == 200
        data = response.get_json()
        assert data["ready"] is True

    def test_not_ready_when_opensearch_disconnected(self, client, mock_opensearch_client):
        """Readiness returns 503 when OpenSearch is unreachable."""
        mock_opensearch_client.ping.return_value = False
        response = client.get("/health/ready")
        assert response.status_code == 503
        data = response.get_json()
        assert data["ready"] is False


class TestMetricsEndpoint:
    """Tests for GET /metrics."""

    def test_metrics_returns_prometheus_format(self, client):
        """Metrics endpoint returns Prometheus text format."""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert b"search_service" in response.data
