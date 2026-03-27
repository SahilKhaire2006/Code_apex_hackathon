import uuid
import json
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter
from core.logger import logger
from core.config import settings
from core.schemas import PolicyChunk, IngestionResult
from core.supabase_client import create_ingestion_session, update_ingestion_session
from agents.ingestion_agent import IngestionAgent
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction


class PolicyPipeline:
    """
    Orchestrates the full policy processing flow:
    PDF → Extract → Chunk → Embed → Store in ChromaDB
    """

    def __init__(self):
        self.ingestion_agent = IngestionAgent()

        # Text splitter — clause-aware chunking
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", ". ", " ", ""]
        )

        # ChromaDB setup
        self.chroma_client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir
        )
        self.embed_fn = SentenceTransformerEmbeddingFunction(
            model_name=settings.embedding_model_name
        )
        self.collection = self.chroma_client.get_or_create_collection(
            name=settings.chroma_collection_name,
            embedding_function=self.embed_fn,
            metadata={"hnsw:space": "cosine"}
        )
        logger.info("PolicyPipeline initialized — ChromaDB collection ready")

    # ── Main entry point ──────────────────────────────────────────

    def run(self, pdf_path: str) -> IngestionResult:
        filename = Path(pdf_path).name
        session_id = create_ingestion_session(filename)
        logger.info(f"Session started: {session_id}")

        try:
            # Step 1: Extract
            extracted = self.ingestion_agent.extract(pdf_path)

            # Step 2: Chunk
            chunks = self._chunk(extracted)

            # Step 3: Embed + Store in ChromaDB
            self._store_in_chromadb(chunks)

            # Step 4: Update Supabase session
            update_ingestion_session(session_id, {
                "total_pages": extracted["total_pages"],
                "total_chunks": len(chunks),
                "status": "COMPLETED"
            })

            result = IngestionResult(
                session_id=session_id,
                filename=filename,
                total_pages=extracted["total_pages"],
                total_chunks=len(chunks),
                status="COMPLETED"
            )
            logger.info(
                f"Pipeline complete — {result.total_pages} pages, "
                f"{result.total_chunks} chunks stored"
            )
            return result

        except Exception as e:
            update_ingestion_session(session_id, {"status": "FAILED"})
            logger.error(f"Pipeline failed: {e}")
            raise

    # ── Chunking ──────────────────────────────────────────────────

    def _chunk(self, extracted: dict) -> list[PolicyChunk]:
        chunks = []
        filename = extracted["filename"]
        chunk_index = 0

        for page in extracted["pages"]:
            page_num = page["page_number"]
            text = page["text"]

            if not text.strip():
                continue

            # Detect section title — first non-empty line of the page
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            section_title = lines[0] if lines else None

            # Split page text into chunks
            page_chunks = self.splitter.split_text(text)

            char_cursor = 0
            for chunk_text in page_chunks:
                char_start = text.find(chunk_text, char_cursor)
                char_end = char_start + len(chunk_text)
                char_cursor = char_end

                chunk = PolicyChunk(
                    chunk_id=str(uuid.uuid4()),
                    text=chunk_text.strip(),
                    page_number=page_num,
                    section_title=section_title,
                    char_start=char_start,
                    char_end=char_end,
                    source_filename=filename,
                    chunk_index=chunk_index
                )
                chunks.append(chunk)
                chunk_index += 1

        logger.info(f"Chunking complete — {len(chunks)} chunks created")
        return chunks

    # ── ChromaDB Storage ──────────────────────────────────────────

    def _store_in_chromadb(self, chunks: list[PolicyChunk]):
        if not chunks:
            logger.warning("No chunks to store")
            return

        # Batch insert for performance
        BATCH_SIZE = 100
        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i:i + BATCH_SIZE]

            self.collection.upsert(
                ids=[c.chunk_id for c in batch],
                documents=[c.text for c in batch],
                metadatas=[{
                    "page_number":    c.page_number,
                    "section_title":  c.section_title or "",
                    "source_filename": c.source_filename,
                    "chunk_index":    c.chunk_index,
                    "char_start":     c.char_start,
                    "char_end":       c.char_end
                } for c in batch]
            )
            logger.info(f"Stored batch {i // BATCH_SIZE + 1} — {len(batch)} chunks")

        logger.info(f"ChromaDB storage complete — {len(chunks)} chunks indexed")

    # ── Retrieval (used by downstream agents) ────────────────────

    def query(self, query_text: str, n_results: int = 5) -> list[dict]:
        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results,
            include=["documents", "metadatas", "distances"]
        )

        retrieved = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0]
        ):
            retrieved.append({
                "text": doc,
                "metadata": meta,
                "relevance_score": round(1 - dist, 4)
            })
        return retrieved

    def get_all_chunks(self) -> list[dict]:
        results = self.collection.get(include=["documents", "metadatas"])
        chunks = []
        for doc, meta in zip(results["documents"], results["metadatas"]):
            chunks.append({"text": doc, "metadata": meta})
        return chunks