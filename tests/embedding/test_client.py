from unittest.mock import MagicMock, patch
from agentdrive.embedding.client import EmbeddingClient


@patch("agentdrive.embedding.client.voyageai.Client")
def test_embed_texts(mock_voyage_cls):
    mock_client = MagicMock()
    mock_client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024, [0.2] * 1024])
    mock_voyage_cls.return_value = mock_client
    client = EmbeddingClient()
    vectors = client.embed(["hello", "world"], input_type="document")
    assert len(vectors) == 2
    assert len(vectors[0]) == 1024


@patch("agentdrive.embedding.client.voyageai.Client")
def test_embed_query(mock_voyage_cls):
    mock_client = MagicMock()
    mock_client.embed.return_value = MagicMock(embeddings=[[0.3] * 1024])
    mock_voyage_cls.return_value = mock_client
    client = EmbeddingClient()
    vector = client.embed_query("search query")
    assert len(vector) == 1024


@patch("agentdrive.embedding.client.voyageai.Client")
def test_truncate_to_256d(mock_voyage_cls):
    mock_client = MagicMock()
    mock_client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
    mock_voyage_cls.return_value = mock_client
    client = EmbeddingClient()
    vectors = client.embed(["hello"], input_type="document")
    truncated = client.truncate(vectors[0], 256)
    assert len(truncated) == 256


@patch("agentdrive.embedding.client.voyageai.Client")
def test_code_model_used_for_code(mock_voyage_cls):
    mock_client = MagicMock()
    mock_client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
    mock_voyage_cls.return_value = mock_client
    client = EmbeddingClient()
    client.embed(["def hello(): pass"], input_type="document", content_type="code")
    call_args = mock_client.embed.call_args
    assert call_args[1]["model"] == "voyage-code-3"
