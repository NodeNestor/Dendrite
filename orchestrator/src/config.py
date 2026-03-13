"""Dendrite configuration — Pydantic settings + runtime overrides."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import Lock

from pydantic_settings import BaseSettings
from pydantic import Field

log = logging.getLogger(__name__)

_CONFIG_FILE = Path("/app/data/config.json")


class LLMConfig(BaseSettings):
    """Config for a single LLM endpoint."""
    provider: str = "vllm"
    model: str = ""
    api_url: str = "http://vllm:8000/v1"
    api_key: str = ""
    max_tokens: int = 16384


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # Bulk model (extraction / triage)
    bulk_provider: str = "vllm"
    bulk_model: str = "Qwen/Qwen3.5-0.8B"
    bulk_api_url: str = "http://vllm:8000/v1"
    bulk_api_key: str = ""
    bulk_max_tokens: int = 16384

    # Synthesis model (cross-validation / report)
    synthesis_provider: str = "vllm"
    synthesis_model: str = "Qwen/Qwen3.5-0.8B"
    synthesis_api_url: str = "http://vllm:8000/v1"
    synthesis_api_key: str = ""
    synthesis_max_tokens: int = 32768

    # GPU
    gpu_memory_utilization: float = 0.92
    gpu_device: str = "GPU-3ad3e2fe"
    kv_cache_dtype: str = "fp8"

    # Services
    searxng_url: str = "http://searxng:8080"
    hivemind_url: str = "http://hiveminddb:8100"

    # Research — tree structure
    max_depth: int = 4                       # max levels deep the tree can grow
    max_branch_iterations: int = 5           # search iterations per branch
    verification_iterations: int = 2         # iterations for verification/counter branches
    queries_per_iteration: int = 4           # search queries generated per iteration

    # Research — search width
    urls_per_iteration: int = 20             # max URLs fetched per branch iteration
    results_per_provider: int = 10           # max search results per provider per query
    max_concurrent_fetches: int = 50         # parallel page downloads
    max_concurrent_llm: int = 100            # parallel LLM calls

    # Research — verification depth
    verification_threshold: float = 0.6      # confidence below this triggers verification
    min_independent_sources: int = 2         # sources needed for auto-verify
    max_concurrent_verifications: int = 3    # parallel cross-validations
    verification_fetch_count: int = 3        # pages fetched per verification check

    # Research — convergence
    min_convergence_iterations: int = 2      # minimum iterations before convergence allowed
    diminishing_returns_threshold: float = 0.10  # new/total claims ratio to stop
    coverage_target: float = 0.85            # LLM coverage score to stop

    # Optional API keys
    github_token: str = ""

    @property
    def bulk_llm(self) -> LLMConfig:
        return LLMConfig(
            provider=self.bulk_provider,
            model=self.bulk_model,
            api_url=self.bulk_api_url,
            api_key=self.bulk_api_key,
            max_tokens=self.bulk_max_tokens,
        )

    @property
    def synthesis_llm(self) -> LLMConfig:
        return LLMConfig(
            provider=self.synthesis_provider,
            model=self.synthesis_model,
            api_url=self.synthesis_api_url,
            api_key=self.synthesis_api_key,
            max_tokens=self.synthesis_max_tokens,
        )


# -- Mutable runtime config -----------------------------------------------

settings = Settings()

_lock = Lock()

_RUNTIME_FIELDS = {
    "bulk_provider", "bulk_model", "bulk_api_url", "bulk_api_key", "bulk_max_tokens",
    "synthesis_provider", "synthesis_model", "synthesis_api_url", "synthesis_api_key",
    "synthesis_max_tokens",
    "hivemind_url", "searxng_url",
    # Tree structure
    "max_depth", "max_branch_iterations", "verification_iterations", "queries_per_iteration",
    # Search width
    "urls_per_iteration", "results_per_provider", "max_concurrent_fetches", "max_concurrent_llm",
    # Verification depth
    "verification_threshold", "min_independent_sources",
    "max_concurrent_verifications", "verification_fetch_count",
    # Convergence
    "min_convergence_iterations", "diminishing_returns_threshold", "coverage_target",
}


def _load_persisted() -> dict:
    if _CONFIG_FILE.exists():
        try:
            return json.loads(_CONFIG_FILE.read_text())
        except Exception as e:
            log.warning("Failed to load persisted config: %s", e)
    return {}


def _save_persisted(data: dict) -> None:
    try:
        _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_FILE.write_text(json.dumps(data, indent=2))
    except Exception as e:
        log.warning("Failed to save config: %s", e)


# Apply persisted overrides on startup
_overrides = _load_persisted()
for k, v in _overrides.items():
    if k in _RUNTIME_FIELDS and hasattr(settings, k):
        object.__setattr__(settings, k, v)


def get_runtime_config() -> dict:
    with _lock:
        result = {}
        for field in sorted(_RUNTIME_FIELDS):
            val = getattr(settings, field, "")
            if "api_key" in field and val:
                result[field] = "***"
            else:
                result[field] = val
        return result


def update_runtime_config(updates: dict) -> dict:
    with _lock:
        current = _load_persisted()
        for key, value in updates.items():
            if key not in _RUNTIME_FIELDS:
                continue
            if "api_key" in key and value == "***":
                continue
            if hasattr(settings, key):
                object.__setattr__(settings, key, value)
                current[key] = value
        _save_persisted(current)
    return get_runtime_config()
