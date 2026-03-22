import logging

import anthropic

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


class EnrichmentClient:
    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def generate_context(self, document_text: str, chunk_text: str) -> str:
        """Generate a context prefix for a chunk using the full document with prompt caching."""
        try:
            response = await self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"<document>\n{document_text}\n</document>",
                                "cache_control": {"type": "ephemeral"},
                            },
                            {
                                "type": "text",
                                "text": CONTEXT_PROMPT.format(chunk_text=chunk_text),
                            },
                        ],
                    }
                ],
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.warning(f"Context generation failed, using empty prefix: {e}")
            return ""

    async def generate_table_questions(self, table_text: str) -> list[str]:
        """Generate synthetic questions for a table chunk."""
        try:
            response = await self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                messages=[
                    {
                        "role": "user",
                        "content": TABLE_QUESTIONS_PROMPT.format(table_text=table_text),
                    }
                ],
            )
            text = response.content[0].text.strip()
            questions = [q.strip().lstrip("0123456789.-) ") for q in text.split("\n") if q.strip()]
            return [q for q in questions if len(q) > 5]
        except Exception as e:
            logger.warning(f"Table question generation failed: {e}")
            return []
