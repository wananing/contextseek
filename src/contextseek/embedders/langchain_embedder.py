"""LangChain embeddings adapter."""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.embeddings import Embeddings


class LangChainEmbedder:
    """Adapt any ``langchain_core.embeddings.Embeddings`` to ``Callable[[str], list[float]]``.

    Works with LangChain embedding providers such as:
      - langchain_openai.OpenAIEmbeddings
      - langchain_huggingface.HuggingFaceEmbeddings
      - langchain_cohere.CohereEmbeddings
      - langchain_aws.BedrockEmbeddings
    """

    # Provider-to-package mapping for install hint generation.
    _PROVIDER_PACKAGES: dict[str, str] = {
        "langchain_openai": "langchain-openai",
        "langchain_ollama": "langchain-ollama",
        "langchain_huggingface": "langchain-huggingface",
        "langchain_cohere": "langchain-cohere",
        "langchain_aws": "langchain-aws",
        "langchain_google_genai": "langchain-google-genai",
        "langchain_anthropic": "langchain-anthropic",
    }

    def __init__(self, embeddings: "Embeddings", *, dims: int) -> None:
        try:
            from langchain_core.embeddings import Embeddings as _Embeddings
        except ImportError as exc:
            raise ImportError(
                "LangChainEmbedder requires langchain-core. "
                "Install with: pip install 'contextseek[langchain]'"
            ) from exc
        if not isinstance(embeddings, _Embeddings):
            module = type(embeddings).__module__.split(".")[0]
            pkg = self._PROVIDER_PACKAGES.get(module, module.replace("_", "-"))
            raise TypeError(
                f"expected langchain_core.embeddings.Embeddings, "
                f"got {type(embeddings).__name__}. "
                f"Make sure you have installed the provider package: "
                f"pip install '{pkg}'"
            )
        self._embeddings = embeddings
        self._dims = dims

    def __call__(self, text: str) -> list[float]:
        return self._embeddings.embed_query(text)

    @property
    def dims(self) -> int:
        return self._dims


__all__ = ["LangChainEmbedder"]
