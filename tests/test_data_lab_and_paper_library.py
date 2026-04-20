from __future__ import annotations

from research_agent.entities import KnowledgeRecord


def _current_user_id(client) -> str:
    me = client.get("/api/auth/me")
    assert me.status_code == 200, me.text
    return me.json()["user"]["id"]


def _openalex_abstract_index(abstract: str) -> dict[str, list[int]]:
    positions: dict[str, list[int]] = {}
    for index, token in enumerate(str(abstract or "").split()):
        positions.setdefault(token, []).append(index)
    return positions


def _upload_csv_asset(client, workspace_id: str, csrf_token: str, *, filename: str = "sample.csv") -> dict:
    payload = (
        b"date,y,x,z\n"
        b"2026-01-01,1,2,3\n"
        b"2026-01-02,2,3,4\n"
        b"2026-01-03,3,4,5\n"
        b"2026-01-04,4,5,6\n"
        b"2026-01-05,5,6,7\n"
        b"2026-01-06,6,7,8\n"
        b"2026-01-07,7,8,9\n"
        b"2026-01-08,8,9,10\n"
        b"2026-01-09,9,10,11\n"
        b"2026-01-10,10,11,12\n"
        b"2026-01-11,11,12,13\n"
        b"2026-01-12,12,13,14\n"
    )
    response = client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        headers={"X-CSRF-Token": csrf_token},
        data={"description": "test dataset"},
        files={"file": (filename, payload, "text/csv")},
    )
    assert response.status_code == 200, response.text
    return response.json()["asset"]


def _openalex_work(
    work_id: str,
    title: str,
    *,
    landing_page_url: str = "",
    pdf_url: str = "",
    year: int = 2026,
    abstract: str = "",
    keywords: list[str] | None = None,
) -> dict:
    payload = {
        "id": f"https://openalex.org/{work_id}",
        "display_name": title,
        "publication_year": year,
        "doi": f"https://doi.org/10.1234/{work_id.lower()}",
        "cited_by_count": 17,
        "authorships": [
            {"author": {"display_name": "Ada Researcher"}},
            {"author": {"display_name": "Ben Analyst"}},
        ],
        "primary_location": {
            "landing_page_url": landing_page_url,
            "pdf_url": pdf_url,
            "source": {"display_name": "Journal of Test Cases"},
        },
        "keywords": [
            {"display_name": keyword}
            for keyword in (keywords or ["economics", "policy"])
        ],
    }
    if abstract.strip():
        payload["abstract_inverted_index"] = _openalex_abstract_index(abstract)
    return payload


def test_data_lab_detail_endpoints_return_ready_payloads(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]
    source_asset = _upload_csv_asset(client, workspace_id, csrf_token)

    prepared = client.post(
        f"/api/workspaces/{workspace_id}/analysis/prepare",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "asset_id": source_asset["id"],
            "workflow_group": "sample_preparation",
            "required_columns": ["y", "x"],
            "numeric_columns": ["y", "x", "z"],
            "variant_label": "manual-processing",
            "variant_spec": {"keep_columns": ["y", "x", "z"]},
        },
    )
    assert prepared.status_code == 200, prepared.text
    prepared_payload = prepared.json()
    prepared_asset_id = prepared_payload["asset"]["id"]

    processing_detail = client.get(f"/api/data-lab/results/processing/{prepared_asset_id}")
    assert processing_detail.status_code == 200, processing_detail.text
    processing_result = processing_detail.json()["result"]
    assert processing_result["status"] == "ready"
    assert processing_result["next_action"] == "open_detail"
    assert processing_result["detail_path"] == f"/data-lab/results/processing/{prepared_asset_id}"
    assert processing_result["asset"]["id"] == prepared_asset_id
    assert processing_result["profile"]["asset"]["id"] == prepared_asset_id
    assert processing_result["workspace_id"] == workspace_id

    modeled = client.post(
        f"/api/workspaces/{workspace_id}/analysis/models",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "asset_id": prepared_asset_id,
            "model_type": "ols",
            "dependent": "y",
            "independents": ["x"],
            "variant_label": "manual-model",
            "variant_spec": {"dependent": "y", "independents": ["x"]},
        },
    )
    assert modeled.status_code == 200, modeled.text
    model_payload = modeled.json()
    model_record_id = model_payload["result_record_id"]

    model_detail = client.get(f"/api/data-lab/results/models/{model_record_id}")
    assert model_detail.status_code == 200, model_detail.text
    detail_payload = model_detail.json()
    assert detail_payload["workspace_id"] == workspace_id
    assert detail_payload["record"]["id"] == model_record_id
    assert detail_payload["result"]["status"] == "ready"
    assert detail_payload["result"]["workflow_type"] == "model"
    assert detail_payload["result"]["model_type"] == "ols"
    assert detail_payload["result"]["result_record_id"] == model_record_id
    assert detail_payload["result"]["detail_path"] == f"/data-lab/results/models/{model_record_id}"
    assert detail_payload["result"]["variant_source"] == "manual-model"
    assert detail_payload["result"]["next_action"] == "open_detail"


def test_optimization_result_list_and_detail_include_ready_fields(client, auth_headers, db_session):
    workspace_id = auth_headers["workspace_id"]
    user_id = _current_user_id(client)

    record = KnowledgeRecord(
        workspace_id=workspace_id,
        owner_user_id=user_id,
        title="Optimization Suite | Fast Sweep",
        content="Optimization summary",
        tags_json=["optimization"],
        metadata_json={
            "workflow_type": "optimization",
            "suite_label": "Fast Sweep",
            "summary": {"headline": "OriginalPSO ranked first."},
            "template_name": "Fast Optimization Template",
            "variant_label": "fast-sweep",
            "variant_spec": {"runs": 1, "epoch": 3},
            "result_detail_path": "/data-lab/results/optimization/custom-opt-record",
        },
    )
    db_session.add(record)
    db_session.commit()

    listed = client.get(f"/api/workspaces/{workspace_id}/optimization/results")
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    item = next(entry for entry in items if entry["id"] == record.id)
    assert item["status"] == "ready"
    assert item["next_action"] == "open_detail"
    assert item["detail_path"] == "/data-lab/results/optimization/custom-opt-record"
    assert item["template_source"] == "Fast Optimization Template"
    assert item["variant_source"] == "fast-sweep"

    detail = client.get(f"/api/optimization/results/{record.id}")
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert payload["workspace_id"] == workspace_id
    assert payload["record"]["id"] == record.id
    assert payload["result"]["status"] == "ready"
    assert payload["result"]["workflow_type"] == "optimization"
    assert payload["result"]["result_record_id"] == record.id
    assert payload["result"]["detail_path"] == "/data-lab/results/optimization/custom-opt-record"
    assert payload["result"]["template_source"] == "Fast Optimization Template"
    assert payload["result"]["variant_source"] == "fast-sweep"


def test_paper_library_reports_missing_blocked_and_ready_pdf_states(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]

    imported = client.post(
        f"/api/workspaces/{workspace_id}/literature/import",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "works": [
                _openalex_work(
                    "WREADY0001",
                    "Ready Paper",
                    landing_page_url="https://example.com/papers/ready",
                    pdf_url="https://example.com/papers/ready.pdf",
                ),
                _openalex_work("WMISSING0001", "Missing PDF Paper"),
                _openalex_work(
                    "WBLOCKED0001",
                    "Blocked PDF Paper",
                    landing_page_url="http://127.0.0.1:9000/paper",
                    pdf_url="http://127.0.0.1:9000/paper.pdf",
                ),
            ]
        },
    )
    assert imported.status_code == 200, imported.text
    items = {item["title"]: item for item in imported.json()["items"]}

    assert items["Ready Paper"]["pdf_import_status"] == "ready"
    assert items["Ready Paper"]["can_import_pdf"] is True
    assert items["Ready Paper"]["pdf_url"] == "https://example.com/papers/ready.pdf"

    assert items["Missing PDF Paper"]["pdf_import_status"] == "missing"
    assert items["Missing PDF Paper"]["can_import_pdf"] is False
    assert items["Missing PDF Paper"]["pdf_import_reason"]

    assert items["Blocked PDF Paper"]["pdf_import_status"] == "blocked"
    assert items["Blocked PDF Paper"]["can_import_pdf"] is False
    assert items["Blocked PDF Paper"]["pdf_url"] == ""
    assert items["Blocked PDF Paper"]["landing_page_url"] == ""

    listed = client.get(f"/api/workspaces/{workspace_id}/literature")
    assert listed.status_code == 200, listed.text
    listed_items = {item["title"]: item for item in listed.json()["items"]}
    assert listed_items["Ready Paper"]["pdf_import_status"] == "ready"
    assert listed_items["Missing PDF Paper"]["pdf_import_status"] == "missing"
    assert listed_items["Blocked PDF Paper"]["pdf_import_status"] == "blocked"


def test_paper_library_import_and_derivation_flows_are_idempotent(client, auth_headers, monkeypatch):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]

    imported = client.post(
        f"/api/workspaces/{workspace_id}/literature/import",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "works": [
                _openalex_work(
                    "WFLOW0001",
                    "Paper Flow Test",
                    landing_page_url="https://example.com/papers/flow",
                    pdf_url="https://example.com/papers/flow.pdf",
                )
            ]
        },
    )
    assert imported.status_code == 200, imported.text
    entry = imported.json()["items"][0]
    entry_id = entry["id"]

    monkeypatch.setattr(
        "research_agent.platform_research._download_pdf_candidate",
        lambda url: (b"%PDF-1.4\n%test pdf\n", url),
    )
    monkeypatch.setattr(
        "research_agent.platform_core.extract_text_from_bytes",
        lambda content, *, filename, content_type="": "stub pdf text",
    )

    imported_pdf = client.post(
        f"/api/workspaces/{workspace_id}/literature/{entry_id}/import-pdf",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert imported_pdf.status_code == 200, imported_pdf.text
    imported_pdf_payload = imported_pdf.json()
    assert imported_pdf_payload["imported"] is True
    assert imported_pdf_payload["asset"]["kind"] == "document_pdf"
    asset_id = imported_pdf_payload["asset"]["id"]

    imported_pdf_again = client.post(
        f"/api/workspaces/{workspace_id}/literature/{entry_id}/import-pdf",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert imported_pdf_again.status_code == 200, imported_pdf_again.text
    assert imported_pdf_again.json()["imported"] is False
    assert imported_pdf_again.json()["asset"]["id"] == asset_id

    imported_knowledge = client.post(
        f"/api/workspaces/{workspace_id}/literature/{entry_id}/import-knowledge",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert imported_knowledge.status_code == 200, imported_knowledge.text
    imported_knowledge_payload = imported_knowledge.json()
    assert imported_knowledge_payload["imported"] is True
    knowledge_record_id = imported_knowledge_payload["record"]["id"]

    imported_knowledge_again = client.post(
        f"/api/workspaces/{workspace_id}/literature/{entry_id}/import-knowledge",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert imported_knowledge_again.status_code == 200, imported_knowledge_again.text
    assert imported_knowledge_again.json()["imported"] is False
    assert imported_knowledge_again.json()["record"]["id"] == knowledge_record_id

    derived = client.post(
        f"/api/workspaces/{workspace_id}/literature/{entry_id}/derive-note",
        headers={"X-CSRF-Token": csrf_token},
        json={"mode": "summary"},
    )
    assert derived.status_code == 200, derived.text
    derived_payload = derived.json()
    assert derived_payload["imported"] is True
    assert derived_payload["mode"] == "summary"
    assert derived_payload["record"]["title"].startswith("Paper Summary:")
    summary_record_id = derived_payload["record"]["id"]

    derived_again = client.post(
        f"/api/workspaces/{workspace_id}/literature/{entry_id}/derive-note",
        headers={"X-CSRF-Token": csrf_token},
        json={"mode": "summary"},
    )
    assert derived_again.status_code == 200, derived_again.text
    assert derived_again.json()["imported"] is False
    assert derived_again.json()["record"]["id"] == summary_record_id

    listed = client.get(f"/api/workspaces/{workspace_id}/literature")
    assert listed.status_code == 200, listed.text
    item = next(row for row in listed.json()["items"] if row["id"] == entry_id)
    assert item["workspace_pdf_asset_id"] == asset_id
    assert item["workspace_knowledge_record_id"] == knowledge_record_id
    assert item["workspace_summary_record_id"] == summary_record_id


def test_paper_library_derived_note_modes_capture_expected_templates(client, auth_headers):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]

    imported = client.post(
        f"/api/workspaces/{workspace_id}/literature/import",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "works": [
                _openalex_work(
                    "WMODES0001",
                    "Derived Note Modes",
                    landing_page_url="https://example.com/papers/modes",
                    pdf_url="https://example.com/papers/modes.pdf",
                    abstract=(
                        "This paper studies how tariff shocks reshape firm pricing, employment, "
                        "and supply-chain exposure using matched customs and payroll records."
                    ),
                    keywords=["tariffs", "employment", "supply chains"],
                )
            ]
        },
    )
    assert imported.status_code == 200, imported.text
    entry = imported.json()["items"][0]
    entry_id = entry["id"]

    base_note = client.post(
        f"/api/workspaces/{workspace_id}/literature/{entry_id}/import-knowledge",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert base_note.status_code == 200, base_note.text
    base_note_payload = base_note.json()
    base_record = base_note_payload["record"]

    expectations = {
        "summary": {
            "title_prefix": "Paper Summary:",
            "tag": "summary-note",
            "sections": [
                "## Paper in one sentence",
                "## Core contribution",
                "## Evidence to verify manually",
                "## Citation",
            ],
        },
        "annotation": {
            "title_prefix": "Paper Annotation Template:",
            "tag": "annotation-template",
            "sections": [
                "## Reading purpose",
                "## Claims to annotate",
                "## Variable and data notes",
                "## Quotations / page notes",
            ],
        },
        "question_breakdown": {
            "title_prefix": "Paper Question Breakdown:",
            "tag": "question-breakdown",
            "sections": [
                "## Central research question",
                "## Sub-questions to inspect",
                "## Variable checklist",
                "## Follow-up searches",
            ],
        },
    }
    record_ids: dict[str, str] = {}

    for mode, expected in expectations.items():
        derived = client.post(
            f"/api/workspaces/{workspace_id}/literature/{entry_id}/derive-note",
            headers={"X-CSRF-Token": csrf_token},
            json={"mode": mode},
        )
        assert derived.status_code == 200, derived.text
        derived_payload = derived.json()
        assert derived_payload["imported"] is True
        assert derived_payload["mode"] == mode
        assert derived_payload["record"]["title"].startswith(expected["title_prefix"])
        record_id = derived_payload["record"]["id"]
        record_ids[mode] = record_id

        detail = client.get(f"/api/workspaces/{workspace_id}/knowledge/{record_id}")
        assert detail.status_code == 200, detail.text
        record = detail.json()["record"]
        assert record["metadata"]["source_type"] == "paper_library"
        assert record["metadata"]["derivative_mode"] == mode
        assert record["metadata"]["literature_entry_id"] == entry_id
        assert record["metadata"]["base_knowledge_record_id"] == base_record["id"]
        assert record["metadata"]["base_knowledge_record_title"] == base_record["title"]
        assert record["metadata"]["pdf_url"] == "https://example.com/papers/modes.pdf"
        assert record["metadata"]["landing_page_url"] == "https://example.com/papers/modes"
        assert expected["tag"] in record["tags"]
        for section in expected["sections"]:
            assert section in record["content"]
        assert "## Traceability" in record["content"]
        assert f"- Source note: {base_record['title']}" in record["content"]

        derived_again = client.post(
            f"/api/workspaces/{workspace_id}/literature/{entry_id}/derive-note",
            headers={"X-CSRF-Token": csrf_token},
            json={"mode": mode},
        )
        assert derived_again.status_code == 200, derived_again.text
        assert derived_again.json()["imported"] is False
        assert derived_again.json()["record"]["id"] == record_id

    listed = client.get(f"/api/workspaces/{workspace_id}/literature")
    assert listed.status_code == 200, listed.text
    listed_entry = next(row for row in listed.json()["items"] if row["id"] == entry_id)
    assert listed_entry["workspace_summary_record_id"] == record_ids["summary"]
    assert listed_entry["workspace_annotation_record_id"] == record_ids["annotation"]
    assert listed_entry["workspace_question_record_id"] == record_ids["question_breakdown"]


def test_paper_library_batch_import_endpoints_report_counts(client, auth_headers, monkeypatch):
    workspace_id = auth_headers["workspace_id"]
    csrf_token = auth_headers["csrf"]

    imported = client.post(
        f"/api/workspaces/{workspace_id}/literature/import",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "works": [
                _openalex_work(
                    "WBATCHREADY1",
                    "Batch Ready Paper",
                    landing_page_url="https://example.com/papers/batch-ready",
                    pdf_url="https://example.com/papers/batch-ready.pdf",
                ),
                _openalex_work("WBATCHMISS1", "Batch Missing Paper"),
                _openalex_work(
                    "WBATCHBLOCK1",
                    "Batch Blocked Paper",
                    landing_page_url="http://127.0.0.1:9999/batch",
                    pdf_url="http://127.0.0.1:9999/batch.pdf",
                ),
            ]
        },
    )
    assert imported.status_code == 200, imported.text
    items = imported.json()["items"]
    ids = [item["id"] for item in items]

    monkeypatch.setattr(
        "research_agent.platform_research._download_pdf_candidate",
        lambda url: (b"%PDF-1.4\n%batch pdf\n", url),
    )
    monkeypatch.setattr(
        "research_agent.platform_core.extract_text_from_bytes",
        lambda content, *, filename, content_type="": "stub pdf text",
    )

    pdf_batch = client.post(
        f"/api/workspaces/{workspace_id}/literature/import-pdfs",
        headers={"X-CSRF-Token": csrf_token},
        json={"entry_ids": ids},
    )
    assert pdf_batch.status_code == 200, pdf_batch.text
    pdf_batch_payload = pdf_batch.json()
    assert pdf_batch_payload["requested_count"] == 3
    assert pdf_batch_payload["imported_count"] == 1
    assert pdf_batch_payload["skipped_count"] == 2
    assert pdf_batch_payload["failed_count"] == 0

    knowledge_batch = client.post(
        f"/api/workspaces/{workspace_id}/literature/import-knowledge",
        headers={"X-CSRF-Token": csrf_token},
        json={"entry_ids": ids},
    )
    assert knowledge_batch.status_code == 200, knowledge_batch.text
    knowledge_batch_payload = knowledge_batch.json()
    assert knowledge_batch_payload["requested_count"] == 3
    assert knowledge_batch_payload["imported_count"] == 3
    assert knowledge_batch_payload["failed_count"] == 0
