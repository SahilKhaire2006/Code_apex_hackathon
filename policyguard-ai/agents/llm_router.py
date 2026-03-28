"""
Layer 5: Parallel Async LLM Router (Together AI → OpenRouter → Groq)
Provides automatic failover between providers with rate limit handling.
5-8 parallel calls per round respecting RPM limits.
"""

import asyncio
import time
import json
import os
import aiohttp
import json_repair
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
from core.config import settings
from core.logger import logger

# ── Provider configurations ────────────────────────────────────────────
# Groq is primary — Together AI key is invalid, OpenRouter as secondary fallback
PROVIDERS = [
    {
        "name":     "bedrock",
        "base_url": "https://bedrock-runtime.us-east-1.amazonaws.com",  # Standard, but boto3 is better. We'll use the token via direct OpenAI client if it's compatible, but wait, the token format implies an OpenAI-compatible proxy or direct API. Let's use the standard OpenAI client format but with the token.
        "api_key":  settings.aws_bearer_token_bedrock,
        "model":    "mistral.mistral-7b-instruct-v0:2",
        "rpm":      50,
        "enabled":  bool(settings.aws_bearer_token_bedrock),
    },
    {
        "name":     "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key":  settings.groq_api_key,
        "model":    "meta-llama/llama-4-scout-17b-16e-instruct",
        "rpm":      30,
        "enabled":  bool(settings.groq_api_key),
    },
    {
        "name":     "openrouter_guard_22m",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key":  settings.openrouter_api_key,
        "model":    "meta-llama/llama-prompt-guard-2-22m",
        "rpm":      100,
        "enabled":  bool(settings.openrouter_api_key),
    },
    {
        "name":     "openrouter_guard_86m",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key":  settings.openrouter_api_key,
        "model":    "meta-llama/llama-prompt-guard-2-86m",
        "rpm":      100,
        "enabled":  bool(settings.openrouter_api_key),
    },
    {
        "name":     "together",
        "base_url": "https://api.together.xyz/v1",
        "api_key":  settings.together_api_key,
        "model":    "meta-llama/Llama-3-8b-chat-hf",
        "rpm":      600,
        "enabled":  bool(settings.together_api_key),
    },
]

# Max parallel calls per provider (stay well under RPM)
PARALLEL_LIMITS = {"bedrock": 4, "groq": 2, "openrouter_guard_22m": 5, "openrouter_guard_86m": 5, "together": 8}

# Seconds to wait between parallel rounds per provider
ROUND_SLEEP = {"bedrock": 2, "groq": 12, "openrouter_guard_22m": 4, "openrouter_guard_86m": 4, "together": 2}


class RateLimitError(Exception):
    """Raised when provider rate limits are hit."""
    def __init__(self, provider_name: str):
        self.provider_name = provider_name
        super().__init__(f"Rate limit on {provider_name}")


class LLMRouter:
    """
    Routes LLM calls across multiple providers with automatic failover.
    Handles rate limiting gracefully by switching providers.
    """

    def __init__(self):
        self.active_providers = [p for p in PROVIDERS if p["enabled"]]
        if not self.active_providers:
            raise RuntimeError(
                "No LLM provider configured. "
                "Set TOGETHER_API_KEY, OPENROUTER_API_KEY, or GROQ_API_KEY in .env"
            )
        primary = self.active_providers[0]["name"]
        names   = [p["name"] for p in self.active_providers]
        logger.info(f"[LLMRouter] Initialized with providers: {names} | Primary: {primary}")

    def get_primary_provider(self) -> dict:
        """Get the primary (first) provider."""
        return self.active_providers[0]

    async def _call_single_batch_async(
        self,
        provider:       dict,
        system_prompt:  str,
        user_message:   str,
        batch_index:    int,
    ) -> List[Dict]:
        """
        Single async LLM call with error handling.
        
        Args:
            provider: Provider config dict
            system_prompt: System prompt for LLM
            user_message: User message with chunks
            batch_index: Index of this batch (for logging)
            
        Returns:
            List of extracted rules
            
        Raises:
            RateLimitError: If provider rate limits
        """
        try:
            if provider["name"] == "bedrock":
                # The user's specific Bedrock gateway token uses Bearer auth with native Mistral payloads
                url = f"{provider['base_url']}/model/{provider['model']}/invoke"
                prompt = f"<s>[INST] {system_prompt}\n\n{user_message} [/INST]"
                
                headers = {
                    "Authorization": f"Bearer {provider['api_key']}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "prompt": prompt,
                    "max_tokens": 4096,
                    "temperature": 0.1,
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json=payload, timeout=45.0) as resp:
                        if resp.status >= 400:
                            if resp.status == 429:
                                raise RateLimitError(provider["name"])
                            body = await resp.text()
                            logger.error(f"[bedrock] HTTP {resp.status}: {body}")
                            resp.raise_for_status()
                        result = await resp.json()
                        outputs = result.get('outputs')
                        
                        if not outputs or not isinstance(outputs, list) or not outputs[0]:
                            logger.error(f"[bedrock] Unexpected API response format: {json.dumps(result)}")
                            raw = "{}"
                        else:
                            raw = outputs[0].get('text', '{}')
            else:
                client = AsyncOpenAI(
                    api_key=provider["api_key"],
                    base_url=provider["base_url"],
                )
                
                resp = await client.chat.completions.create(
                    model=provider["model"],
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_message},
                    ],
                    temperature=0.1,
                    max_tokens=4096,
                )
                raw = resp.choices[0].message.content or "{}"
                
            # Strip markdown code fences if model wraps JSON in them
            if "```" in raw:
                import re
                match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
                raw = match.group(1).strip() if match else raw
                
            try:
                parsed = json_repair.loads(raw) if isinstance(raw, str) else raw
            except Exception as e:
                logger.error(f"[{provider['name']}] Failed to repair JSON: {e}")
                parsed = {}
                
            rules  = parsed.get("rules", []) if isinstance(parsed, dict) else []
            
            logger.info(f"[{provider['name']}] Batch {batch_index}: "
                       f"Successfully extracted {len(rules)} rules")
            return rules

        except Exception as e:
            error = str(e).lower()
            is_rate = any(x in error for x in ["429", "rate", "quota", "limit", 
                                                "rate_limit", "too many requests"])
            
            if is_rate:
                logger.warning(f"[{provider['name']}] Rate limit on batch {batch_index}")
                raise RateLimitError(provider["name"])
            
            logger.error(f"[{provider['name']}] Batch {batch_index} error: {type(e).__name__}: {e}")
            return []

    async def extract_all_batches_async(
        self,
        batches:        List[List[Dict]],
        system_prompt:  str,
        progress_cb:    Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Processes all batches in parallel rounds with automatic failover.
        If primary provider rate limits, remaining batches go to next provider.
        
        Args:
            batches: List of batches from adaptive_batcher
            system_prompt: System prompt for rule extraction
            progress_cb: Optional async callback for progress updates
            
        Returns:
            {"rules": [...], "total": N, "provider": "...", "stats": {...}}
        """
        all_rules       = []
        provider_index  = 0
        total_batches   = len(batches)
        completed       = 0

        # Group batches into processing queue
        batch_queue = list(enumerate(batches))   # (original_index, batch)

        while batch_queue and provider_index < len(self.active_providers):
            provider    = self.active_providers[provider_index]
            max_parallel = PARALLEL_LIMITS.get(provider["name"], 3)
            sleep_time   = ROUND_SLEEP.get(provider["name"], 5)

            logger.info(f"[LLMRouter] Processing with {provider['name']} | "
                       f"{len(batch_queue)} batches remaining | "
                       f"Max parallel: {max_parallel}")

            failed_batches = []

            # Process in parallel rounds
            for round_start in range(0, len(batch_queue), max_parallel):
                round_items = batch_queue[round_start:round_start + max_parallel]

                # Build async tasks for this round
                tasks = []
                for orig_idx, batch in round_items:
                    user_msg = self._build_user_message(batch, orig_idx, total_batches)
                    task = asyncio.create_task(
                        self._call_single_batch_async(
                            provider, system_prompt, user_msg, orig_idx
                        )
                    )
                    tasks.append((orig_idx, batch, task))

                # Run round concurrently
                results = await asyncio.gather(
                    *[t for _, _, t in tasks],
                    return_exceptions=True,
                )

                # Process results
                for (orig_idx, batch, _), result in zip(tasks, results):
                    if isinstance(result, RateLimitError):
                        failed_batches.append((orig_idx, batch))
                        logger.debug(f"[LLMRouter] Batch {orig_idx} failed (rate limit)")
                    elif isinstance(result, Exception):
                        failed_batches.append((orig_idx, batch))
                        logger.debug(f"[LLMRouter] Batch {orig_idx} failed (exception)")
                    elif isinstance(result, list):
                        all_rules.extend(result)
                        completed += 1
                        
                        if progress_cb:
                            try:
                                await progress_cb({
                                    "completed":   completed,
                                    "total":       total_batches,
                                    "rules_found": len(all_rules),
                                    "provider":    provider["name"],
                                    "percent":     int(completed / total_batches * 100),
                                })
                            except Exception as e:
                                logger.warning(f"[LLMRouter] Progress callback error: {e}")

                # Sleep between rounds to respect rate limits
                if round_start + max_parallel < len(batch_queue):
                    logger.debug(f"[LLMRouter] Sleeping {sleep_time}s before next round")
                    await asyncio.sleep(sleep_time)

            # Move to next provider if batches failed
            batch_queue = failed_batches
            provider_index += 1

            if batch_queue and provider_index < len(self.active_providers):
                next_name = self.active_providers[provider_index]["name"]
                logger.warning(
                    f"[LLMRouter] {len(batch_queue)} batches failed on "
                    f"{provider['name']}. Switching to {next_name}."
                )

        # Log final status
        if batch_queue:
            logger.error(f"[LLMRouter] FAILED: {len(batch_queue)} batches exhausted all providers")
        else:
            logger.info(f"[LLMRouter] SUCCESS: All {total_batches} batches processed")

        return {
            "rules":     all_rules,
            "total":     len(all_rules),
            "provider":  self.active_providers[0]["name"],
            "completed_batches": completed,
            "failed_batches": len(batch_queue),
            "stats": {
                "total_batches": total_batches,
                "successful": completed,
                "failed": len(batch_queue),
            }
        }

    def _build_user_message(self, batch: List[Dict],
                            idx: int, total: int) -> str:
        """Build user message with chunks for LLM extraction."""
        lines = [
            f"Extract compliance rules from {len(batch)} policy text chunks.",
            f"Batch {idx+1} of {total}.",
            f"Document: Policy/Regulation Extract",
            "",
        ]
        for i, chunk in enumerate(batch):
            text = chunk.get("text", "")
            page = chunk.get("page", chunk.get("metadata", {}).get("page", 0))
            para = chunk.get("paragraph_number", "")
            
            lines.append(f"--- CHUNK {i+1} | Page {page}"
                        f"{' | ' + para if para else ''} ---")
            lines.append(text.strip())
            lines.append(f"--- END CHUNK {i+1} ---")
            lines.append("")
        
        lines.append('Return JSON: {"rules": [{"title": "...", "description": "...", '
                    '"severity": "CRITICAL|HIGH|MEDIUM|LOW", "source_clause": "...", '
                    '"page_number": <int>, "paragraph_number": "..."}]}')
        return "\n".join(lines)

    def route_prompt(self, prompt: str, fallback_provider: str = "groq") -> str:
        """
        Synchronous single-prompt LLM call — tries each active provider in order.
        Used by rule_checker for violation matrix generation (runs in thread executor).
        Returns raw text response from the first successful provider.
        """
        import requests

        # Sort so that the fallback_provider is tried first
        providers = sorted(
            self.active_providers,
            key=lambda p: 0 if p["name"] == fallback_provider else 1
        )

        for provider in providers:
            try:
                if provider["name"] == "bedrock":
                    # Bedrock uses a direct HTTP call with Bearer auth
                    url = f"{provider['base_url']}/model/{provider['model']}/invoke"
                    instruct_prompt = f"<s>[INST] {prompt} [/INST]"
                    headers = {
                        "Authorization": f"Bearer {provider['api_key']}",
                        "Content-Type": "application/json"
                    }
                    payload = {"prompt": instruct_prompt, "max_tokens": 2048, "temperature": 0.1}
                    resp = requests.post(url, headers=headers, json=payload, timeout=30)
                    resp.raise_for_status()
                    data = resp.json()
                    outputs = data.get("outputs", [])
                    if outputs:
                        return outputs[0].get("text", "")
                else:
                    # OpenAI-compatible providers: Groq, OpenRouter, Together
                    headers = {
                        "Authorization": f"Bearer {provider['api_key']}",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "model": provider["model"],
                        "messages": [
                            {"role": "system", "content": "You are a precise financial compliance auditor. Respond only with valid JSON."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.1,
                        "max_tokens": 2048
                    }
                    resp = requests.post(
                        f"{provider['base_url']}/chat/completions",
                        headers=headers, json=payload, timeout=30
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    logger.info(f"[LLMRouter.route_prompt] Success via {provider['name']}")
                    return content

            except Exception as e:
                logger.warning(f"[LLMRouter.route_prompt] {provider['name']} failed: {e}")
                continue

        logger.error("[LLMRouter.route_prompt] All providers failed")
        return ""
