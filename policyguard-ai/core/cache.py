"""
Layer 7: Redis Cache + File-Based Fallback + SSE Progress System
Provides instant repeat responses for same-PDF uploads.
File-based cache works on any EC2 instance without Redis setup.
SSE streams progress events to frontend in real-time.
"""

import hashlib
import json
import os
import asyncio
from typing import Optional, List, Dict
from pathlib import Path
from core.logger import logger

# Use file-based cache if Redis not available (works on any EC2)
CACHE_DIR = Path("./registry/cache")


def get_pdf_hash(pdf_path: str) -> str:
    """
    SHA-256 hash of PDF content = unique cache key.
    Returns first 16 chars for readable file names.
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        16-character hex string
    """
    sha256 = hashlib.sha256()
    try:
        with open(pdf_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        hash_val = sha256.hexdigest()[:16]
        logger.debug(f"[Cache] PDF hash: {hash_val} for {Path(pdf_path).name}")
        return hash_val
    except Exception as e:
        logger.error(f"[Cache] Error computing hash for {pdf_path}: {e}")
        return None


def get_cached_rules(pdf_hash: str) -> Optional[List[Dict]]:
    """
    Return cached rules if available, None otherwise.
    
    Args:
        pdf_hash: 16-char hash from get_pdf_hash()
        
    Returns:
        List of rules or None if not cached
    """
    cache_file = CACHE_DIR / f"{pdf_hash}.json"
    try:
        if cache_file.exists():
            with open(cache_file) as f:
                data = json.load(f)
            logger.info(f"[Cache] HIT for {pdf_hash}: {data.get('total', 0)} rules "
                       f"(instant response)")
            return data.get("rules", [])
    except Exception as e:
        logger.warning(f"[Cache] Error reading cache for {pdf_hash}: {e}")
    
    return None


def cache_rules(pdf_hash: str, rules: List[Dict]):
    """
    Save extracted rules to file cache.
    
    Args:
        pdf_hash: 16-char hash from get_pdf_hash()
        rules: List of extracted rule dicts
    """
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = CACHE_DIR / f"{pdf_hash}.json"
        
        with open(cache_file, "w") as f:
            json.dump({
                "rules": rules,
                "total": len(rules),
                "cached_at": str(Path(cache_file).stat().st_mtime if cache_file.exists() else "")
            }, f, indent=2)
        
        logger.info(f"[Cache] Saved {len(rules)} rules for {pdf_hash} to {cache_file}")
    except Exception as e:
        logger.error(f"[Cache] Error saving rules for {pdf_hash}: {e}")


def clear_cache_file(pdf_hash: str):
    """Remove cache file for a specific PDF."""
    cache_file = CACHE_DIR / f"{pdf_hash}.json"
    try:
        if cache_file.exists():
            cache_file.unlink()
            logger.info(f"[Cache] Cleared cache for {pdf_hash}")
    except Exception as e:
        logger.error(f"[Cache] Error clearing cache for {pdf_hash}: {e}")


def get_cache_stats() -> Dict:
    """Get cache usage statistics."""
    try:
        if not CACHE_DIR.exists():
            return {"cached_pdfs": 0, "total_rules": 0, "cache_size_kb": 0}
        
        files = list(CACHE_DIR.glob("*.json"))
        total_rules = 0
        total_size = 0
        
        for file in files:
            total_size += file.stat().st_size
            try:
                with open(file) as f:
                    data = json.load(f)
                    total_rules += data.get("total", 0)
            except:
                pass
        
        return {
            "cached_pdfs": len(files),
            "total_rules": total_rules,
            "cache_size_kb": total_size / 1024,
        }
    except Exception as e:
        logger.error(f"[Cache] Error getting stats: {e}")
        return {}


# ── SSE Progress Stream ────────────────────────────────────────────────

class ProgressQueue:
    """Thread-safe queue for progress events during PDF processing."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.queue = asyncio.Queue()
        self.is_closed = False
    
    async def put(self, event: Dict):
        """Add a progress event."""
        if not self.is_closed:
            await self.queue.put(event)
    
    async def get(self) -> Dict:
        """Get next progress event."""
        return await self.queue.get()
    
    async def close(self):
        """Signal end of stream."""
        self.is_closed = True
        await self.queue.put({"done": True})


# Global session queues (could be stored in Redis for distributed systems)
_session_queues: Dict[str, ProgressQueue] = {}


def get_session_queue(session_id: str) -> ProgressQueue:
    """Get or create progress queue for a session."""
    if session_id not in _session_queues:
        _session_queues[session_id] = ProgressQueue(session_id)
    return _session_queues[session_id]


async def progress_generator(session_id: str):
    """
    Yields SSE events as extraction progresses.
    Connects to /progress/{session_id} endpoint on frontend.
    """
    queue = get_session_queue(session_id)
    
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=60.0)
            
            if event.get("done"):
                logger.info(f"[SSE] Progress stream closed for {session_id}")
                break
            
            # Format as Server-Sent Event
            yield f"data: {json.dumps(event)}\n\n"
            
        except asyncio.TimeoutError:
            # Send heartbeat to keep connection alive
            yield "data: {\"heartbeat\": true}\n\n"
        except Exception as e:
            logger.error(f"[SSE] Error in progress_generator: {e}")
            break


def log_progress(session_id: str, stage: str, **kwargs):
    """
    Log a progress event with stage and additional data.
    This is a synchronous wrapper that schedules the async put.
    
    Args:
        session_id: Session ID
        stage: Progress stage (e.g., "classification", "chunking", "extraction")
        **kwargs: Additional event data
    """
    queue = get_session_queue(session_id)
    event = {
        "stage": stage,
        "timestamp": __import__("time").time(),
        **kwargs
    }
    
    try:
        # Try to put async (if in async context)
        asyncio.create_task(queue.put(event))
    except RuntimeError:
        # Fall back to creating new event loop if needed
        logger.debug(f"[Progress] {stage}: {kwargs}")
