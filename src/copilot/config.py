"""Central settings, loaded from .env so secrets never live in code."""
from dataclasses import dataclass
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


def _get(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None or value == "":
        raise RuntimeError(f"Missing setting {name} — add it to your .env file")
    return value


@dataclass(frozen=True)
class Settings:
    llm_base_url: str
    llm_api_key: str
    chat_model: str
    pg_dsn: str
    embedding_model: str


def postgres_dsn() -> str:
    """DB connection string only — usable without LLM settings."""
    return (
        f"host={_get('POSTGRES_HOST', 'localhost')} "
        f"port={_get('POSTGRES_PORT', '5432')} "
        f"dbname={_get('POSTGRES_DB', 'copilot')} "
        f"user={_get('POSTGRES_USER', 'copilot')} "
        f"password={_get('POSTGRES_PASSWORD')}"
    )


def load_settings() -> Settings:
    return Settings(
        llm_base_url=_get("LLM_BASE_URL"),
        llm_api_key=_get("LLM_API_KEY"),
        chat_model=_get("LLM_CHAT_MODEL"),
        pg_dsn=postgres_dsn(),
        embedding_model=_get("EMBEDDING_MODEL", "BAAI/bge-m3"),
    )


def llm_client(settings: Settings | None = None) -> OpenAI:
    """OpenAI-compatible client.

    Azure OpenAI v1 API uses the standard OpenAI client with
    base_url = https://<resource>.openai.azure.com/openai/v1/ and no api-version.
    The same code works with any other OpenAI-compatible provider.
    """
    s = settings or load_settings()
    return OpenAI(base_url=s.llm_base_url, api_key=s.llm_api_key)
