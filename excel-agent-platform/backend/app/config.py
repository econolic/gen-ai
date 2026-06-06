from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(default="openai/gpt-5-mini", alias="OPENROUTER_MODEL")
    serper_api_key: str | None = Field(default=None, alias="SERPER_API_KEY")
    langchain_api_key: str | None = Field(default=None, alias="LANGCHAIN_API_KEY")
    data_dir: Path = Field(default=PROJECT_ROOT / "data", alias="DATA_DIR")
    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    enable_chroma_memory: bool = Field(default=False, alias="ENABLE_CHROMA_MEMORY")
    chroma_dir: Path | None = Field(default=None, alias="CHROMA_DIR")
    tool_timeout_seconds: float = Field(default=12.0, ge=1.0, alias="TOOL_TIMEOUT_SECONDS")
    tool_retry_count: int = Field(default=1, ge=0, alias="TOOL_RETRY_COUNT")
    offline_demo_seed_first: bool = Field(default=False, alias="OFFLINE_DEMO_SEED_FIRST")
    enrichment_concurrency: int = Field(default=8, ge=1, alias="ENRICHMENT_CONCURRENCY")
    graph_fanout_threshold: int = Field(default=1000, ge=1, alias="GRAPH_FANOUT_THRESHOLD")
    graph_chunk_size: int = Field(default=1000, ge=1, alias="GRAPH_CHUNK_SIZE")
    graph_fanout_concurrency: int = Field(default=4, ge=1, alias="GRAPH_FANOUT_CONCURRENCY")
    mcp_excel_url: str | None = Field(default=None, alias="MCP_EXCEL_URL")
    mcp_calc_url: str | None = Field(default=None, alias="MCP_CALC_URL")
    mcp_source_url: str | None = Field(default=None, alias="MCP_SOURCE_URL")
    mcp_search_url: str | None = Field(default=None, alias="MCP_SEARCH_URL")
    mcp_strict_tools: bool = Field(default=False, alias="MCP_STRICT_TOOLS")
    backend_cors_origins: str = Field(
        default="http://localhost:5173",
        alias="BACKEND_CORS_ORIGINS",
    )

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def app_db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def resolved_chroma_dir(self) -> Path:
        return self.chroma_dir or self.data_dir / "chroma"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    def ensure_data_dirs(self) -> None:
        for path in [self.uploads_dir, self.outputs_dir, self.reports_dir, self.cache_dir]:
            path.mkdir(parents=True, exist_ok=True)
        if self.enable_chroma_memory:
            self.resolved_chroma_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_data_dirs()
    return settings
