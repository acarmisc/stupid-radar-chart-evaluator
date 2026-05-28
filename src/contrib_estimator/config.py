"""Runtime config from env vars. All overridable via CLI flags."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # LiteLLM gateway
    litellm_base_url: str
    litellm_key: str
    model_classify: str
    model_reduce: str

    # Sampling guards
    max_chunks: int
    max_file_kb: int
    max_tokens_budget: int
    seed: int

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            litellm_base_url=os.environ.get("LITELLM_BASE_URL", "http://localhost:4000"),
            litellm_key=os.environ.get("LITELLM_KEY", ""),
            model_classify=os.environ.get("MODEL_CLASSIFY", "anthropic/claude-haiku-4-5"),
            model_reduce=os.environ.get("MODEL_REDUCE", "anthropic/claude-opus-4-7"),
            max_chunks=int(os.environ.get("MAX_CHUNKS", "200")),
            max_file_kb=int(os.environ.get("MAX_FILE_KB", "100")),
            max_tokens_budget=int(os.environ.get("MAX_TOKENS_BUDGET", "500000")),
            seed=int(os.environ.get("SEED", "42")),
        )
