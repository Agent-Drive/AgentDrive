"""Knowledge base compilation pipeline.

Stub module — full implementation in Task 8.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


async def compile_kb(kb_id: UUID, session: AsyncSession) -> None:
    """Compile a knowledge base from its source files into articles.

    This is a stub — the real implementation will be added in Task 8.
    """
    raise NotImplementedError("compile_kb not yet implemented (Task 8)")
