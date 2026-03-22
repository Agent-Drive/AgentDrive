import json
from agentdrive.chunking.structured import StructuredChunker


def test_supported_types():
    chunker = StructuredChunker()
    assert "json" in chunker.supported_types()
    assert "yaml" in chunker.supported_types()


def test_json_top_level_keys():
    data = json.dumps({"database": {"host": "localhost", "port": 5432}, "api": {"endpoints": ["/users", "/auth"]}, "logging": {"level": "info"}}, indent=2)
    chunker = StructuredChunker()
    results = chunker.chunk(data, "config.json")
    all_content = " ".join(c.content for g in results for c in g.children)
    assert "database" in all_content
    assert "localhost" in all_content


def test_key_path_in_context():
    data = json.dumps({"database": {"host": "localhost"}}, indent=2)
    chunker = StructuredChunker()
    results = chunker.chunk(data, "config.json")
    prefixes = [c.context_prefix for g in results for c in g.children]
    assert any("config.json" in p for p in prefixes)


def test_small_json_single_chunk():
    data = json.dumps({"key": "value"})
    chunker = StructuredChunker()
    results = chunker.chunk(data, "small.json")
    total_children = sum(len(g.children) for g in results)
    assert total_children == 1


def test_yaml_handled():
    yaml_content = "database:\n  host: localhost\n  port: 5432\napi:\n  key: secret\n"
    chunker = StructuredChunker()
    results = chunker.chunk(yaml_content, "config.yaml")
    assert len(results) >= 1
