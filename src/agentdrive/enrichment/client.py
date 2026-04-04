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

GROUP_SUMMARY_PROMPT = """You are summarizing section {group_index} of {total_groups} of a larger document. Produce:
1. A summary of this section (2-3 sentences)
2. section_summaries (a list of objects with "heading" and "summary" for each major section within this portion)

<document_section>
{group_text}
</document_section>

Return valid JSON with this exact structure:
{{"summary": "...", "section_summaries": [{{"heading": "...", "summary": "..."}}]}}"""

REDUCE_SUMMARY_PROMPT = """Below are summaries of consecutive sections of a large document. Synthesize them into:
1. A document_summary (2-3 sentences describing the document's purpose, parties involved, and subject matter)
2. section_summaries (a merged, deduplicated list of objects with "heading" and "summary" covering the entire document)

{group_summaries_text}

Return valid JSON with this exact structure:
{{"document_summary": "...", "section_summaries": [{{"heading": "...", "summary": "..."}}]}}"""


class EnrichmentClient:
    def __init__(self) -> None:
        self._client = openai.AsyncOpenAI(
            api_key=settings.enrichment_api_key,
            base_url=settings.enrichment_base_url,
            timeout=30.0,
        )

    async def generate_context(self, document_text: str, chunk_text: str) -> str:
        """Generate a context prefix for a chunk using the full document."""
        try:
            response = await self._client.chat.completions.create(
                model=settings.enrichment_model,
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
                model=settings.enrichment_model,
                max_tokens=16384,
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

    async def generate_group_summary(
        self, group_text: str, group_index: int, total_groups: int
    ) -> dict:
        """Summarize a group of parent chunks (map phase of hierarchical summarization)."""
        try:
            response = await self._client.chat.completions.create(
                model=settings.enrichment_model,
                max_tokens=16384,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "user",
                        "content": GROUP_SUMMARY_PROMPT.format(
                            group_text=group_text,
                            group_index=group_index,
                            total_groups=total_groups,
                        ),
                    }
                ],
            )
            text = (response.choices[0].message.content or "").strip()
            return json.loads(text)
        except Exception as e:
            logger.warning(f"Group summary generation failed: {e}")
            return {"summary": "", "section_summaries": []}

    async def generate_reduce_summary(self, group_summaries: list[dict]) -> dict:
        """Synthesize group summaries into a final document summary (reduce phase)."""
        parts = []
        for i, group in enumerate(group_summaries, 1):
            sections_text = "\n".join(
                f"  - {s['heading']}: {s['summary']}"
                for s in group.get("section_summaries", [])
            )
            parts.append(
                f"Group {i} (of {len(group_summaries)}):\n"
                f"Summary: {group.get('summary', '')}\n"
                f"Sections:\n{sections_text}"
            )
        group_summaries_text = "\n\n".join(parts)

        try:
            response = await self._client.chat.completions.create(
                model=settings.enrichment_model,
                max_tokens=16384,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "user",
                        "content": REDUCE_SUMMARY_PROMPT.format(
                            group_summaries_text=group_summaries_text
                        ),
                    }
                ],
            )
            text = (response.choices[0].message.content or "").strip()
            return json.loads(text)
        except Exception as e:
            logger.warning(f"Reduce summary generation failed: {e}")
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
                model=settings.enrichment_model,
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
                model=settings.enrichment_model,
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

    async def extract_concepts(
        self,
        summaries: str,
        existing_titles: list[str],
    ) -> list[dict]:
        """Phase 5a: Extract key concepts from document summaries."""
        existing = ", ".join(existing_titles) if existing_titles else "None"
        prompt = f"""Analyze these document summaries and identify the key concepts, topics, and ideas that should have their own knowledge base article.

Existing articles (do not duplicate): {existing}

Document summaries:
{summaries}

Return a JSON object with a "concepts" key containing an array. For each concept:
{{"concepts": [{{"concept_name": "...", "description": "one sentence description", "is_new": true}}]}}

For existing concepts needing update, set is_new to false and include existing_article_title.
If no concepts found, return {{"concepts": []}}.
"""
        try:
            response = await self._client.chat.completions.create(
                model=settings.enrichment_model,
                max_tokens=4096,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
            )
            text = (response.choices[0].message.content or "").strip()
            result = json.loads(text)
            return result.get("concepts", result if isinstance(result, list) else [])
        except Exception as e:
            logger.warning(f"Concept extraction failed: {e}")
            return []

    async def generate_article(
        self,
        concept_name: str,
        concept_description: str,
        relevant_chunks: list[dict],
        existing_article: str | None = None,
    ) -> dict:
        """Phase 5b: Generate or update an article for a concept."""
        chunks_text = "\n\n---\n\n".join(
            f"[Chunk {c['chunk_id']}]\n{c['content']}" for c in relevant_chunks
        )
        update_ctx = ""
        if existing_article:
            update_ctx = (
                f"\n\nExisting article to update:\n{existing_article}\n\n"
                "Incorporate new information while preserving accurate existing content."
            )

        prompt = f"""Write a comprehensive knowledge base article about: {concept_name}
Description: {concept_description}
{update_ctx}
Source material:
{chunks_text}

Return valid JSON:
{{"title": "...", "content": "markdown article body", "category": "topic category", "source_refs": [{{"chunk_id": "...", "excerpt": "relevant excerpt from chunk"}}]}}

Every claim must be traceable to a source chunk. source_refs must reference actual chunk IDs from above.
"""
        try:
            response = await self._client.chat.completions.create(
                model=settings.enrichment_model,
                max_tokens=8192,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
            )
            text = (response.choices[0].message.content or "").strip()
            return json.loads(text)
        except Exception as e:
            logger.warning(f"Article generation failed for '{concept_name}': {e}")
            return {"title": concept_name, "content": "", "category": "", "source_refs": []}

    async def discover_connections(
        self,
        article_summaries: list[dict],
    ) -> list[dict]:
        """Phase 5c: Discover connections between articles."""
        summaries_text = "\n".join(
            f"- {a['title']}: {a['summary']}" for a in article_summaries
        )
        prompt = f"""Analyze these knowledge base articles and identify non-obvious connections.

Articles:
{summaries_text}

Return a JSON object with a "connections" key:
{{"connections": [{{"source_title": "...", "target_title": "...", "link_type": "related|contradicts|extends|prerequisite", "rationale": "brief explanation"}}]}}

Link types: related (connected, no dependency), contradicts (conflicting info), extends (builds upon), prerequisite (required knowledge).
Only significant, non-obvious connections. Return {{"connections": []}} if none.
"""
        try:
            response = await self._client.chat.completions.create(
                model=settings.enrichment_model,
                max_tokens=4096,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
            )
            text = (response.choices[0].message.content or "").strip()
            result = json.loads(text)
            return result.get("connections", result if isinstance(result, list) else [])
        except Exception as e:
            logger.warning(f"Connection discovery failed: {e}")
            return []
