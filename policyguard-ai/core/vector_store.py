"""
Vector Store wrapper using ChromaDB for semantic search of compliance rules.
"""

import os
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Optional
from core.logger import logger
from core.config import settings

class RuleVectorStore:
    def __init__(self):
        # Ensure directory exists
        os.makedirs(settings.cache_dir, exist_ok=True)
        db_path = os.path.join(settings.cache_dir, "chroma_db")
        
        # Initialize persistent client
        self.client = chromadb.PersistentClient(path=db_path)
        
        # Get or create collection
        self.collection_name = "policy_rules"
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"[VectorStore] Initialized ChromaDB at {db_path} | Collection: {self.collection_name}")

    def upsert_rules(self, rules: List[Dict], tenant_id: str = "global_rbi"):
        """
        Embeds and stores rules in the vector database.
        Includes tenant_id and status in metadata for filtering.
        """
        if not rules:
            return

        ids = []
        documents = []
        metadatas = []

        for rule in rules:
            # We embed the combination of title + description + source clause
            text_to_embed = f"Title: {rule.get('title', '')}\nDescription: {rule.get('description', '')}\nSource: {rule.get('source_clause', '')}"
            
            ids.append(rule["id"])
            documents.append(text_to_embed)
            
            metadatas.append({
                "tenant_id": tenant_id,
                "status": rule.get("status", "ACTIVE"),
                "severity": rule.get("severity", "MEDIUM"),
                "title": rule.get("title", "") or "",
                "page_number": rule.get("page_number") or -1
            })

        self.collection.upsert(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        logger.info(f"[VectorStore] Upserted {len(rules)} rules for tenant {tenant_id}")

    def search_similar_rules(self, query_text: str, tenant_id: str = "global_rbi", limit: int = 3) -> List[Dict]:
        """
        Searches for semantically similar ACTIVE rules for the given tenant.
        """
        try:
            results = self.collection.query(
                query_texts=[query_text],
                n_results=limit,
                where={
                    "$and": [
                        {"tenant_id": tenant_id},
                        {"status": "ACTIVE"}
                    ]
                }
            )

            # Format results
            matches = []
            if results["ids"] and len(results["ids"]) > 0:
                for i in range(len(results["ids"][0])):
                    match = {
                        "id": results["ids"][0][i],
                        "document": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i],
                        "distance": results["distances"][0][i] if "distances" in results else 0
                    }
                    matches.append(match)
            return matches
            
        except Exception as e:
            logger.error(f"[VectorStore] Search failed: {e}")
            return []

# Singleton instance
vector_store = RuleVectorStore()
