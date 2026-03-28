from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import fitz
import requests

from .models import PdfExtract, ResearchArtifact, WorkRecord
from .utils import (
    reconstruct_abstract,
    truncate_text,
    unique_preserve_order,
    work_to_bibtex,
    write_json,
)


OPENALEX_WORKS_API = "https://api.openalex.org/works"
DEFAULT_HEADERS = {
    "User-Agent": "research-agent/0.1 (academic-research-cli)",
    "Accept": "application/json",
}


class ResearchSession:
    def __init__(self, session_dir: Path) -> None:
        self.session_dir = session_dir
        self.downloads_dir = session_dir / "downloads"
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.sources: dict[str, WorkRecord] = {}
        self.consulted_source_ids: list[str] = []
        self._source_counter = 0
        self.http = requests.Session()
        self.http.headers.update(DEFAULT_HEADERS)

    def _next_source_id(self) -> str:
        self._source_counter += 1
        return f"S{self._source_counter}"

    def _register_work(self, raw_work: dict[str, Any]) -> WorkRecord:
        openalex_id = raw_work.get("id", "")
        for record in self.sources.values():
            if record.openalex_id == openalex_id:
                return record

        authors = [
            authorship.get("author", {}).get("display_name", "")
            for authorship in raw_work.get("authorships", [])
            if authorship.get("author", {}).get("display_name")
        ]
        topics = [
            topic.get("display_name", "")
            for topic in raw_work.get("topics", [])[:6]
            if topic.get("display_name")
        ]
        keywords = [
            keyword.get("display_name", "")
            for keyword in raw_work.get("keywords", [])[:10]
            if keyword.get("display_name")
        ]
        source_id = self._next_source_id()
        best_oa_location = raw_work.get("best_oa_location") or {}
        primary_location = raw_work.get("primary_location") or {}
        primary_source = (
            best_oa_location.get("source", {}).get("display_name")
            or primary_location.get("source", {}).get("display_name")
        )
        venue = (
            primary_location.get("source", {}).get("display_name")
            or best_oa_location.get("source", {}).get("display_name")
        )
        record = WorkRecord(
            source_id=source_id,
            openalex_id=openalex_id,
            title=raw_work.get("display_name", "Untitled"),
            authors=authors,
            abstract=reconstruct_abstract(raw_work.get("abstract_inverted_index")),
            publication_year=raw_work.get("publication_year"),
            publication_date=raw_work.get("publication_date"),
            cited_by_count=raw_work.get("cited_by_count", 0),
            doi=raw_work.get("doi"),
            pdf_url=best_oa_location.get("pdf_url")
            or primary_location.get("pdf_url")
            or raw_work.get("open_access", {}).get("oa_url"),
            landing_page_url=best_oa_location.get("landing_page_url")
            or primary_location.get("landing_page_url"),
            primary_location_source=primary_source,
            venue=venue,
            type=raw_work.get("type"),
            topics=topics,
            keywords=keywords,
            raw=raw_work,
        )
        self.sources[source_id] = record
        return record

    def _mark_consulted(self, source_ids: list[str]) -> None:
        self.consulted_source_ids = unique_preserve_order(
            [*self.consulted_source_ids, *source_ids]
        )

    def search_openalex(
        self,
        query: str,
        max_results: int = 8,
        from_year: int | None = None,
        to_year: int | None = None,
        open_access_only: bool = False,
        require_pdf: bool = False,
        sort_by: str = "relevance",
    ) -> dict[str, Any]:
        filters = ["has_abstract:true", "is_retracted:false"]
        if open_access_only:
            filters.append("open_access.is_oa:true")
        if require_pdf:
            filters.append("has_pdf_url:true")
        if from_year:
            filters.append(f"from_publication_date:{from_year}-01-01")
        if to_year:
            filters.append(f"to_publication_date:{to_year}-12-31")

        params = {
            "search": query,
            "filter": ",".join(filters),
            "per-page": max(1, min(max_results, 25)),
        }
        if sort_by == "most_cited":
            params["sort"] = "cited_by_count:desc"
        response = self.http.get(OPENALEX_WORKS_API, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        records = [self._register_work(item) for item in payload.get("results", [])]
        source_ids = [record.source_id for record in records]
        self._mark_consulted(source_ids)
        return {
            "query": query,
            "result_count": len(records),
            "source_ids": source_ids,
            "results": [record.short_dict() for record in records],
        }

    def get_source_details(self, source_id: str) -> dict[str, Any]:
        record = self._require_source(source_id)
        self._mark_consulted([source_id])
        return {
            "source": record.model_dump(mode="json"),
            "recommendation": (
                "Use the abstract and topics for screening. Fetch the PDF only if the abstract "
                "suggests strong relevance or if the method section matters."
            ),
        }

    def fetch_pdf_excerpt(
        self,
        source_id: str,
        max_pages: int = 6,
        max_characters: int = 12000,
    ) -> dict[str, Any]:
        record = self._require_source(source_id)
        if not record.pdf_url:
            return {
                "source_id": source_id,
                "status": "no_pdf_url",
                "message": "No open-access PDF URL is available for this source.",
            }

        pdf_path = self.downloads_dir / f"{source_id}.pdf"
        if not pdf_path.exists():
            response = self.http.get(record.pdf_url, timeout=60)
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")
            content = response.content
            if "pdf" not in content_type.lower() and not content.startswith(b"%PDF"):
                return {
                    "source_id": source_id,
                    "status": "unsupported_content",
                    "message": f"URL did not return a PDF. Content-Type: {content_type}",
                    "url": record.pdf_url,
                }
            pdf_path.write_bytes(content)

        extract = self._extract_pdf_text(source_id, pdf_path, max_pages, max_characters)
        self._mark_consulted([source_id])
        return {
            "source_id": source_id,
            "status": "ok",
            "file_path": str(extract.file_path),
            "page_count": extract.page_count,
            "extracted_pages": extract.extracted_pages,
            "text_excerpt": extract.text_excerpt,
        }

    def export_bibtex(self, source_ids: list[str]) -> dict[str, Any]:
        records = [self._require_source(source_id) for source_id in source_ids]
        bibtex_entries = [work_to_bibtex(record) for record in records]
        return {
            "source_ids": source_ids,
            "bibtex": "\n\n".join(bibtex_entries),
        }

    def save_report(
        self,
        topic: str,
        markdown_content: str,
        source_ids: list[str],
    ) -> dict[str, Any]:
        ordered_source_ids = unique_preserve_order(source_ids)
        artifact = self.persist_outputs(topic=topic, report_markdown=markdown_content, source_ids=ordered_source_ids)
        return {
            "status": "saved",
            "report_path": str(artifact.report_path),
            "bibtex_path": str(artifact.bibtex_path),
            "sources_path": str(artifact.sources_path),
            "source_ids": ordered_source_ids,
        }

    def persist_outputs(
        self,
        topic: str,
        report_markdown: str,
        source_ids: list[str],
    ) -> ResearchArtifact:
        report_path = self.session_dir / "report.md"
        bibtex_path = self.session_dir / "references.bib"
        sources_path = self.session_dir / "sources.json"

        records = [self.sources[source_id] for source_id in source_ids if source_id in self.sources]
        report_path.write_text(report_markdown.strip() + "\n", encoding="utf-8")
        bibtex_path.write_text(
            "\n\n".join(work_to_bibtex(record) for record in records).strip() + "\n",
            encoding="utf-8",
        )
        write_json(
            sources_path,
            {
                "topic": topic,
                "source_ids": source_ids,
                "sources": [record.model_dump(mode="json") for record in records],
            },
        )
        return ResearchArtifact(
            report_path=report_path,
            bibtex_path=bibtex_path,
            sources_path=sources_path,
            source_ids=source_ids,
        )

    def serialize_consulted_sources(self) -> list[dict[str, Any]]:
        return [
            self.sources[source_id].short_dict()
            for source_id in self.consulted_source_ids
            if source_id in self.sources
        ]

    def available_source_ids(self) -> list[str]:
        return list(self.sources.keys())

    def _require_source(self, source_id: str) -> WorkRecord:
        if source_id not in self.sources:
            raise KeyError(
                f"Unknown source_id {source_id!r}. Search first and use one of: {sorted(self.sources)}"
            )
        return self.sources[source_id]

    def _extract_pdf_text(
        self,
        source_id: str,
        pdf_path: Path,
        max_pages: int,
        max_characters: int,
    ) -> PdfExtract:
        excerpts: list[str] = []
        with fitz.open(pdf_path) as document:
            page_count = document.page_count
            extracted_pages = min(page_count, max_pages)
            for page_index in range(extracted_pages):
                page_text = document.load_page(page_index).get_text("text")
                page_text = truncate_text(page_text, limit=max_characters)
                excerpts.append(f"[Page {page_index + 1}]\n{page_text}")
        excerpt_text = truncate_text("\n\n".join(excerpts), limit=max_characters)
        return PdfExtract(
            source_id=source_id,
            file_path=pdf_path,
            page_count=page_count,
            extracted_pages=extracted_pages,
            text_excerpt=excerpt_text,
        )


def tool_result_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)
