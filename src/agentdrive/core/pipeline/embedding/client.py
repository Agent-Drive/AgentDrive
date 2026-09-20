import voyageai
from agentdrive.config import settings

DOC_MODEL = "voyage-4"
CODE_MODEL = "voyage-code-3"
QUERY_MODEL = "voyage-4-lite"


class EmbeddingClient:
    def __init__(self) -> None:
        self._client = voyageai.Client(api_key=settings.voyage_api_key)

    def embed(self, texts: list[str], input_type: str = "document", content_type: str = "text") -> list[list[float]]:
        model = CODE_MODEL if content_type == "code" else DOC_MODEL
        result = self._client.embed(texts, model=model, input_type=input_type)
        return result.embeddings

    def embed_query(self, query: str) -> list[float]:
        result = self._client.embed([query], model=QUERY_MODEL, input_type="query")
        return result.embeddings[0]

    def truncate(self, vector: list[float], dimensions: int) -> list[float]:
        return vector[:dimensions]
