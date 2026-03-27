from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # LLM
    groq_api_key: str
    huggingface_api_token: str | None = None

    # ChromaDB
    chroma_persist_dir: str = "./vector_store"
    chroma_collection_name: str = "policy_clauses"
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Supabase
    supabase_url: str
    supabase_key: str

    # Registry
    rules_registry_json: str = "./registry/rules.json"

    # Paths
    policy_pdf_dir: str = "./data/policy_pdfs"
    transaction_csv_dir: str = "./data/transactions"
    reports_dir: str = "./reports"

    # App
    app_env: str = "development"
    log_level: str = "INFO"

    class Config:
        env_file = ".env"

settings = Settings()