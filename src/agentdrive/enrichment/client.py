import json
import logging

import openai

from agentdrive.config import settings

logger = logging.getLogger(__name__)

CONTEXT_PROMPT = """Here is the chunk we want to situate within the whole document:
<chunk>
{chunk_text}
</chunk>
Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk. Answer only with the succinct context and nothing else."""

TABLE_QUESTIONS_PROMPT = """Given this table from a document:
<table>
{table_text}
</table>
Generate 5-8 natural language questions that someone might ask that this table could answer. Return only the questions, one per line."""

SUMMARY_PROMPT = """Analyze this document and produce:
1. A document_summary (2-3 sentences describing the document's purpose, parties involved, and subject matter)
2. section_summaries (a list of objects with "heading" and "summary" for each major section)

<document>
{document_text}
</document>

Return valid JSON with this exact structure:
{{"document_summary": "...", "section_summaries": [{{"heading": "...", "summary": "..."}}]}}"""

CONTEXT_WITH_SUMMARY_PROMPT = """Document summary: {doc_summary}

Section context: {section_summary}

Nearby content:
{neighbors}

Here is the chunk we want to situate:
<chunk>
{chunk_text}
</chunk>
Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk. Answer only with the succinct context and nothing else."""


class EnrichmentClient:
    def __init__(self) -> None:
        self._client = openai.AsyncOpenAI(
            api_key=settings.baseten_api_key,
            base_url=settings.baseten_base_url,
            timeout=30.0,
        )

    async def generate_context(self, document_text: str, chunk_text: str) -> str:
        """Generate a context prefix for a chunk using the full document."""
        try:
            response = await self._client.chat.completions.create(
                model=settings.baseten_model,
                max_tokens=200,
                messages=[
                    {
                        "role": "user",
                        "content": f"<document>\n{document_text}\n</document>\n\n{CONTEXT_PROMPT.format(chunk_text=chunk_text)}",
                    }
                ],
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            logger.warning(f"Context generation failed, using empty prefix: {e}")
            return ""

    async def generate_summary(self, document_text: str) -> dict:
        """Generate a document summary and section summaries."""
        try:
            response = await self._client.chat.completions.create(
                model=settings.baseten_model,
                max_tokens=1000,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "user",
                        "content": SUMMARY_PROMPT.format(document_text=document_text),
                    }
                ],
            )
            text = (response.choices[0].message.content or "").strip()
            return json.loads(text)
        except Exception as e:
            logger.warning(f"Summary generation failed: {e}")
            return {"document_summary": "", "section_summaries": []}

    async def generate_context_with_summary(
        self,
        doc_summary: str,
        section_summary: str,
        neighbors: str,
        chunk_text: str,
    ) -> str:
        """Generate a context prefix using document summary and local context."""
        try:
            response = await self._client.chat.completions.create(
                model=settings.baseten_model,
                max_tokens=200,
                messages=[
                    {
                        "role": "user",
                        "content": CONTEXT_WITH_SUMMARY_PROMPT.format(
                            doc_summary=doc_summary,
                            section_summary=section_summary,
                            neighbors=neighbors,
                            chunk_text=chunk_text,
                        ),
                    }
                ],
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            logger.warning(f"Context generation with summary failed: {e}")
            return ""

    async def generate_table_questions(self, table_text: str) -> list[str]:
        """Generate synthetic questions for a table chunk."""
        try:
            response = await self._client.chat.completions.create(
                model=settings.baseten_model,
                max_tokens=500,
                messages=[
                    {
                        "role": "user",
                        "content": TABLE_QUESTIONS_PROMPT.format(table_text=table_text),
                    }
                ],
            )
            text = (response.choices[0].message.content or "").strip()
            questions = [q.strip().lstrip("0123456789.-) ") for q in text.split("\n") if q.strip()]
            return [q for q in questions if len(q) > 5]
        except Exception as e:
            logger.warning(f"Table question generation failed: {e}")
            return []
