from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "path",
    [
        "/data-lab",
        "/data-lab/preparation",
        "/data-lab/results/models/demo-model-result",
        "/optimization-lab",
        "/optimization-lab/results/demo-optimization-result",
    ],
)
def test_legacy_lab_routes_keep_anonymous_auth_redirect(client, path: str):
    response = client.get(path, follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/"


@pytest.mark.parametrize(
    ("path", "location"),
    [
        ("/data-lab", "/app/data-lab/dataset"),
        ("/data-lab/preparation?step=clean", "/app/data-lab/preparation?step=clean"),
        ("/data-lab/model", "/app/data-lab/model"),
        ("/data-lab/results", "/app/data-lab/results"),
        ("/data-lab/history", "/app/data-lab/history"),
        ("/data-lab/optimization", "/app/data-lab/optimization"),
        ("/data-lab/processing/sample_preparation", "/app/data-lab/preparation?family=sample_preparation"),
        ("/data-lab/models/econometrics_baseline", "/app/data-lab/model?family=econometrics_baseline"),
        (
            "/data-lab/models/econometrics_baseline/ols",
            "/app/data-lab/model?family=econometrics_baseline&method=ols",
        ),
        (
            "/data-lab/learn/models/econometrics_baseline/ols",
            "/app/data-lab/model?family=econometrics_baseline&method=ols&learn=1",
        ),
        ("/data-lab/results/processing/prepared-1", "/app/data-lab/results?type=processing&id=prepared-1"),
        ("/data-lab/results/models/model-1", "/app/data-lab/results?type=models&id=model-1"),
        ("/data-lab/results/optimization/opt-1", "/app/data-lab/results?type=optimization&id=opt-1"),
        ("/optimization-lab", "/app/data-lab/optimization"),
        ("/optimization-lab/results/opt-1", "/app/data-lab/results?type=optimization&id=opt-1"),
    ],
)
def test_legacy_lab_routes_redirect_authenticated_users_to_spa(client, auth_headers, path: str, location: str):
    response = client.get(path, follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == location


def test_legacy_lab_detail_routes_keep_authenticated_not_found(client, auth_headers):
    response = client.get("/data-lab/models/not-a-family", follow_redirects=False)

    assert response.status_code == 404


def test_provider_catalog_alias_matches_existing_provider_endpoint(client, auth_headers):
    legacy_response = client.get("/api/providers")
    alias_response = client.get("/api/provider-catalog")

    assert legacy_response.status_code == 200
    assert alias_response.status_code == 200
    assert alias_response.json() == legacy_response.json()


def test_provider_catalog_alias_keeps_anonymous_api_protection(client):
    response = client.get("/api/provider-catalog")

    assert response.status_code == 401
