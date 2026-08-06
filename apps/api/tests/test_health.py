from fastapi.testclient import TestClient

from project_manager_api.main import app


def test_health_endpoint_reports_service_status() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "project-manager-api",
        "status": "ok",
    }
