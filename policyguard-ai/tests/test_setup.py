# tests/test_setup.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chromadb
import pymupdf
import pdfplumber
import pandas as pd
import pandera
import langchain
from langchain_huggingface import HuggingFaceEmbeddings
import groq
import fastapi
from pydantic import BaseModel
from loguru import logger
from core.supabase_client import get_supabase

def test_imports():
    logger.info("Testing all imports...")
    print(f"  ChromaDB     : {chromadb.__version__}")
    print(f"  LangChain    : {langchain.__version__}")
    print(f"  Pandas       : {pd.__version__}")
    print(f"  FastAPI      : {fastapi.__version__}")
    print(f"  HF Embeddings: Loaded")
    logger.info("All imports successful")

def test_supabase():
    logger.info("Testing Supabase connection...")
    client = get_supabase()
    # Ping the rules_registry table
    response = client.table("rules_registry").select("id").limit(1).execute()
    logger.info(f"Supabase connected — rules_registry reachable")
    print(f"  Supabase     : Connected")

if __name__ == "__main__":
    test_imports()
    test_supabase()
    print("\n✅ Environment fully ready — proceed to Step 2")