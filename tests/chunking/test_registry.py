from agentdrive.chunking.registry import ChunkerRegistry


def test_registry_returns_chunker_for_type():
    registry = ChunkerRegistry()
    chunker = registry.get_chunker("markdown")
    assert chunker is not None
    assert "markdown" in chunker.supported_types()


def test_registry_returns_text_for_unknown():
    registry = ChunkerRegistry()
    chunker = registry.get_chunker("unknown_type")
    assert chunker is not None
    assert "text" in chunker.supported_types()


def test_registry_all_types_covered():
    registry = ChunkerRegistry()
    for content_type in ["pdf", "markdown", "code", "json", "yaml", "csv", "xlsx", "notebook", "text"]:
        chunker = registry.get_chunker(content_type)
        assert chunker is not None
