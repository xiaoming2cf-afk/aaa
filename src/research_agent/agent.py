from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from openai import OpenAI
from openai.types.responses import Response, ResponseFunctionToolCall
from rich.console import Console

from .config import Settings
from .prompts import SYSTEM_INSTRUCTIONS
from .research_tools import ResearchSession, tool_result_json
from .utils import extract_source_ids, unique_preserve_order


ToolHandler = Callable[..., dict[str, Any]]
ToolEventHandler = Callable[[dict[str, Any]], None]


@dataclass
class AgentRunResult:
    final_text: str
    report_path: str
    bibtex_path: str
    sources_path: str
    used_source_ids: list[str]
    tool_trace: list[dict[str, Any]]


class AcademicResearchAgent:
    def __init__(
        self,
        *,
        settings: Settings,
        session: ResearchSession,
        console: Console | None = None,
        tool_event_handler: ToolEventHandler | None = None,
    ) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required to run the research agent.")
        self.settings = settings
        self.session = session
        self.console = console or Console()
        self.client = OpenAI(api_key=settings.openai_api_key)
        self._saved_paths: dict[str, str] = {}
        self._current_topic = "Academic Research Report"
        self._tool_trace: list[dict[str, Any]] = []
        self._tool_event_handler = tool_event_handler
        self._tool_specs = self._build_tool_specs()
        self._handlers = self._build_handlers()

    def run(
        self,
        *,
        topic: str,
        research_question: str | None = None,
        preferred_language: str = "Chinese",
    ) -> AgentRunResult:
        self._current_topic = topic
        self._tool_trace = []
        user_prompt = self._build_user_prompt(
            topic=topic,
            research_question=research_question,
            preferred_language=preferred_language,
        )

        response = self.client.responses.create(
            model=self.settings.model,
            instructions=SYSTEM_INSTRUCTIONS,
            input=user_prompt,
            tools=self._tool_specs,
            reasoning={"effort": self.settings.reasoning_effort},
            max_tool_calls=self.settings.max_tool_calls,
            parallel_tool_calls=False,
        )

        loop_guard = 0
        while True:
            loop_guard += 1
            if loop_guard > self.settings.max_tool_calls + 3:
                raise RuntimeError("Agent exceeded the safe tool-call loop limit.")

            tool_outputs = self._execute_function_calls(response)
            if not tool_outputs:
                break

            response = self.client.responses.create(
                model=self.settings.model,
                instructions=SYSTEM_INSTRUCTIONS,
                previous_response_id=response.id,
                input=tool_outputs,
                tools=self._tool_specs,
                reasoning={"effort": self.settings.reasoning_effort},
                max_tool_calls=self.settings.max_tool_calls,
                parallel_tool_calls=False,
            )

        final_text = self._get_output_text(response).strip()
        cited_source_ids = extract_source_ids(final_text)
        used_source_ids = unique_preserve_order(cited_source_ids or self.session.consulted_source_ids)

        if not self._saved_paths:
            artifact = self.session.persist_outputs(
                topic=topic,
                report_markdown=final_text,
                source_ids=used_source_ids,
            )
            self._saved_paths = {
                "report_path": str(artifact.report_path),
                "bibtex_path": str(artifact.bibtex_path),
                "sources_path": str(artifact.sources_path),
            }

        return AgentRunResult(
            final_text=final_text,
            report_path=self._saved_paths["report_path"],
            bibtex_path=self._saved_paths["bibtex_path"],
            sources_path=self._saved_paths["sources_path"],
            used_source_ids=used_source_ids,
            tool_trace=list(self._tool_trace),
        )

    def _build_user_prompt(
        self,
        *,
        topic: str,
        research_question: str | None,
        preferred_language: str,
    ) -> str:
        prompt_lines = [
            f"Research topic: {topic}",
            f"Write the final report in {preferred_language}.",
            "Be concrete and evidence-driven.",
            "Use the available tools to identify, inspect, and compare relevant papers.",
        ]
        if research_question:
            prompt_lines.append(f"Primary research question: {research_question}")
        prompt_lines.append(
            "Cite source IDs inline. Save the report before you finish."
        )
        return "\n".join(prompt_lines)

    def _execute_function_calls(self, response: Response) -> list[dict[str, Any]]:
        outputs: list[dict[str, Any]] = []
        for item in response.output:
            if getattr(item, "type", None) != "function_call":
                continue

            call = item
            if not isinstance(call, ResponseFunctionToolCall):
                continue
            tool_name = call.name
            arguments = json.loads(call.arguments or "{}")
            self.console.print(f"[bold cyan]tool[/bold cyan] {tool_name}({arguments})")
            self._record_tool_event(
                {
                    "stage": "requested",
                    "tool": tool_name,
                    "arguments": arguments,
                }
            )
            result = self._invoke_tool(tool_name, arguments)
            self._record_tool_event(
                {
                    "stage": "completed",
                    "tool": tool_name,
                    "arguments": arguments,
                    "result_preview": self._preview_tool_result(result),
                }
            )
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": tool_result_json(result),
                }
            )
        return outputs

    def _invoke_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handler = self._handlers[tool_name]
        try:
            result = handler(**arguments)
            return result
        except Exception as exc:  # pragma: no cover - defensive branch
            return {
                "status": "error",
                "tool": tool_name,
                "message": str(exc),
            }

    def _record_tool_event(self, payload: dict[str, Any]) -> None:
        self._tool_trace.append(payload)
        if self._tool_event_handler is not None:
            self._tool_event_handler(payload)

    def _preview_tool_result(self, result: dict[str, Any]) -> dict[str, Any]:
        preview = dict(result)
        if "text_excerpt" in preview:
            excerpt = str(preview["text_excerpt"])
            preview["text_excerpt"] = excerpt[:500] + ("..." if len(excerpt) > 500 else "")
        if "results" in preview and isinstance(preview["results"], list):
            preview["results"] = preview["results"][:3]
        if "bibtex" in preview:
            preview["bibtex"] = str(preview["bibtex"])[:500]
        if "markdown_content" in preview:
            preview["markdown_content"] = str(preview["markdown_content"])[:500]
        return preview

    def _build_handlers(self) -> dict[str, ToolHandler]:
        return {
            "search_openalex": self.session.search_openalex,
            "get_source_details": self.session.get_source_details,
            "fetch_pdf_excerpt": self.session.fetch_pdf_excerpt,
            "export_bibtex": self.session.export_bibtex,
            "save_report": self._save_report,
        }

    def _save_report(self, markdown_content: str, source_ids: list[str]) -> dict[str, Any]:
        artifact = self.session.save_report(
            topic=self._current_topic,
            markdown_content=markdown_content,
            source_ids=source_ids,
        )
        self._saved_paths = {
            "report_path": artifact["report_path"],
            "bibtex_path": artifact["bibtex_path"],
            "sources_path": artifact["sources_path"],
        }
        return artifact

    def _build_tool_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": "search_openalex",
                "description": "Search scholarly literature in OpenAlex and return candidate papers with source IDs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "integer", "minimum": 1, "maximum": 15},
                        "from_year": {"type": "integer"},
                        "to_year": {"type": "integer"},
                        "open_access_only": {"type": "boolean"},
                        "require_pdf": {"type": "boolean"},
                        "sort_by": {
                            "type": "string",
                            "enum": ["relevance", "most_cited"],
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "get_source_details",
                "description": "Inspect a previously discovered paper in more detail using its source ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_id": {"type": "string"},
                    },
                    "required": ["source_id"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "fetch_pdf_excerpt",
                "description": "Download an open-access PDF for a source and extract text from the first pages.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_id": {"type": "string"},
                        "max_pages": {"type": "integer", "minimum": 1, "maximum": 12},
                        "max_characters": {"type": "integer", "minimum": 1000, "maximum": 30000},
                    },
                    "required": ["source_id"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "export_bibtex",
                "description": "Generate BibTeX entries for selected source IDs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                        },
                    },
                    "required": ["source_ids"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
            {
                "type": "function",
                "name": "save_report",
                "description": "Persist the final markdown report and export the associated bibliography files.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "markdown_content": {"type": "string"},
                        "source_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["markdown_content", "source_ids"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        ]

    def _get_output_text(self, response: Response) -> str:
        if getattr(response, "output_text", ""):
            return response.output_text

        chunks: list[str] = []
        for item in response.output:
            if getattr(item, "type", None) != "message":
                continue
            for content in getattr(item, "content", []):
                if getattr(content, "type", None) == "output_text":
                    chunks.append(content.text)
        return "\n".join(chunks)
