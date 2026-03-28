from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class WorkRecord(BaseModel):
    source_id: str
    openalex_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    abstract: str = ""
    publication_year: int | None = None
    publication_date: str | None = None
    cited_by_count: int = 0
    doi: str | None = None
    pdf_url: str | None = None
    landing_page_url: str | None = None
    primary_location_source: str | None = None
    venue: str | None = None
    type: str | None = None
    topics: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)

    def short_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "authors": self.authors,
            "publication_year": self.publication_year,
            "cited_by_count": self.cited_by_count,
            "doi": self.doi,
            "venue": self.venue,
            "topics": self.topics,
            "pdf_url": self.pdf_url,
            "landing_page_url": self.landing_page_url,
            "abstract": self.abstract,
        }


class PdfExtract(BaseModel):
    source_id: str
    file_path: Path
    page_count: int
    extracted_pages: int
    text_excerpt: str


class ResearchArtifact(BaseModel):
    report_path: Path
    bibtex_path: Path
    sources_path: Path
    source_ids: list[str] = Field(default_factory=list)

