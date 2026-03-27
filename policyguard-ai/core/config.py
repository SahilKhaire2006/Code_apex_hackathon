from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", extra="allow")
    
    # LLM - Multiple Providers
    groq_api_key: str = ""
    openrouter_api_key: str = ""
    together_api_key: str = ""
    huggingface_api_token: str | None = None
    serper_api_key: str = ""

    # ChromaDB
    chroma_persist_dir: str = "./vector_store"
    chroma_collection_name: str = "policy_clauses"
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Supabase (optional — not required for the 8-layer pipeline)
    supabase_url: str = ""
    supabase_key: str = ""

    # Registry
    rules_registry_json: str = "./registry/rules.json"

    # Paths
    policy_pdf_dir: str = "./data/policy_pdfs"
    transaction_csv_dir: str = "./data/transactions"
    reports_dir: str = "./reports"
    cache_dir: str = "./registry/cache"

    # LLM Router settings
    primary_provider: str = "together"  # together | openrouter | groq
    enable_verification: bool = True
    verification_provider: str = "groq"

    # App
    app_env: str = "development"
    log_level: str = "INFO"

settings = Settings()