"""
集中配置 — pydantic-settings

环境变量前缀 RAG_，字段与 backend/.env.example 一一对应。
根目录 .env 仅 docker compose 使用，本模块不读取。
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="RAG_",
        extra="ignore",
    )

    # ----- 应用 -----
    app_name: str = "计算机学院智能问答系统"
    debug: bool = False
    api_prefix: str = "/api"
    chat_history_window: int = Field(default=4, ge=0, description="按 session_id 加载的最近对话轮数")

    # ----- MySQL（凭证见 backend/.env；与根目录 docker .env 中 MYSQL_* 对齐）-----
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "rag_user"
    mysql_password: str = ""  # 生产通过 RAG_MYSQL_PASSWORD 注入，勿在代码写死
    mysql_database: str = "rag_school"
    mysql_pool_size: int = 5

    @property
    def mysql_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            "?charset=utf8mb4"
        )

    # ----- Milvus -----
    milvus_host: str = "127.0.0.1"
    milvus_port: int = 19530
    milvus_collection: str = "child_chunks"
    milvus_dim: int = 1024  # BGE-large 维度，按实际模型调整
    milvus_timeout_seconds: float = Field(default=10.0, gt=0)

    # ----- LLM（百炼 deepseek 直连） -----
    llm_api_key: str = ""
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "deepseek-v3"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 2048
    llm_mock: bool = True  # True 时不调真实 API，返回桩文本

    # ----- Embedding（BGE） -----
    embedding_model: str = "BAAI/bge-large-zh-v1.5"
    embedding_dim: int = Field(default=1024, gt=0, description="Embedding 向量维度，必须与 Milvus 向量维度一致")
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_timeout_seconds: float = Field(default=30.0, gt=0)
    embedding_batch_size: int = Field(default=8, gt=0)
    embedding_mock: bool = True

    # ----- Rerank（qwen3-rerank） -----
    rerank_model: str = "qwen3-rerank"
    rerank_api_key: str = ""
    rerank_base_url: str = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
    rerank_mock: bool = True

    # ----- 检索超参 -----
    top_k_vector: int = Field(default=20, description="Milvus 子块召回数")
    top_k_parent: int = Field(default=8, description="父块聚合保留数")
    top_k_rerank: int = Field(default=5, description="精排后保留数")
    hybrid_vector_weight: float = 0.6
    hybrid_lexical_weight: float = 0.4
    sibling_boost: float = 0.05
    min_score_threshold: float = 0.35
    faq_match_threshold: float = 0.85

    # ----- CORS（前端本地开发） -----
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
