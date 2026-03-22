import re
from agentdrive.chunking.base import ChunkResult, ParentChildChunks
from agentdrive.chunking.tokens import count_tokens

SENTENCE_PATTERN = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')

def split_sentences(text: str) -> list[str]:
    sentences = SENTENCE_PATTERN.split(text)
    return [s.strip() for s in sentences if s.strip()]

def build_parent_child_chunks(
    text: str,
    content_type: str,
    context_prefix: str,
    parent_max_tokens: int = 1500,
    child_max_tokens: int = 300,
    min_child_tokens: int = 50,
    overlap_tokens: int = 30,
) -> list[ParentChildChunks]:
    text = text.strip()
    if not text:
        return []

    total_tokens = count_tokens(text)

    # If text fits in a single child, return as-is
    if total_tokens <= child_max_tokens:
        chunk = ChunkResult(
            content=text, context_prefix=context_prefix,
            token_count=total_tokens, content_type=content_type,
        )
        return [ParentChildChunks(parent=chunk, children=[chunk])]

    # Split into sentences for sentence-aligned chunking
    sentences = split_sentences(text)
    if not sentences:
        sentences = [text]

    # Build children by accumulating sentences
    children: list[ChunkResult] = []
    current_sentences: list[str] = []
    current_tokens = 0
    overlap_sentences: list[str] = []

    for sentence in sentences:
        sentence_tokens = count_tokens(sentence)

        if current_tokens + sentence_tokens > child_max_tokens and current_sentences:
            child_text = " ".join(current_sentences)
            children.append(ChunkResult(
                content=child_text, context_prefix=context_prefix,
                token_count=count_tokens(child_text), content_type=content_type,
            ))

            overlap_sentences = []
            overlap_count = 0
            for s in reversed(current_sentences):
                s_tokens = count_tokens(s)
                if overlap_count + s_tokens > overlap_tokens:
                    break
                overlap_sentences.insert(0, s)
                overlap_count += s_tokens

            current_sentences = list(overlap_sentences)
            current_tokens = overlap_count

        current_sentences.append(sentence)
        current_tokens += sentence_tokens

    if current_sentences:
        child_text = " ".join(current_sentences)
        child_tokens = count_tokens(child_text)
        if child_tokens >= min_child_tokens or not children:
            children.append(ChunkResult(
                content=child_text, context_prefix=context_prefix,
                token_count=child_tokens, content_type=content_type,
            ))
        elif children:
            prev = children[-1]
            merged = prev.content + " " + child_text
            children[-1] = ChunkResult(
                content=merged, context_prefix=context_prefix,
                token_count=count_tokens(merged), content_type=content_type,
            )

    # Build parent(s)
    results: list[ParentChildChunks] = []
    parent_children: list[ChunkResult] = []
    parent_tokens = 0

    for child in children:
        if parent_tokens + child.token_count > parent_max_tokens and parent_children:
            parent_text = " ".join(c.content for c in parent_children)
            parent = ChunkResult(
                content=parent_text, context_prefix=context_prefix,
                token_count=count_tokens(parent_text), content_type=content_type,
            )
            results.append(ParentChildChunks(parent=parent, children=list(parent_children)))
            parent_children = []
            parent_tokens = 0

        parent_children.append(child)
        parent_tokens += child.token_count

    if parent_children:
        parent_text = " ".join(c.content for c in parent_children)
        parent = ChunkResult(
            content=parent_text, context_prefix=context_prefix,
            token_count=count_tokens(parent_text), content_type=content_type,
        )
        results.append(ParentChildChunks(parent=parent, children=list(parent_children)))

    return results
