"""
Layer 6: Two-Pass Verifier for CRITICAL Rules
Re-checks threshold values and source clauses against actual page text.
Catches hallucinated thresholds while saving costs (only verifies CRITICAL/HIGH rules).
"""

import json
import os
import requests
import json_repair
from typing import List, Dict
from openai import OpenAI
from core.config import settings
from core.logger import logger

VERIFY_PROMPT = """You are verifying a single compliance rule extracted from a policy document.

Check if the rule's source_clause actually appears verbatim (or nearly verbatim) in the page text provided.
Also verify that any numeric thresholds or deadlines in the rule match what is written in the page text.

RULE TO VERIFY:
{rule_json}

PAGE TEXT WHERE RULE WAS FOUND (Page {page_number}):
{page_text}

Answer with ONLY this JSON:
{{
  "source_clause_found": true or false,
  "thresholds_correct": true or false,
  "verified_source_clause": "the exact sentence from page text that supports this rule, or null",
  "correction_needed": null or "what is wrong and what the correct value should be"
}}"""


class TwoPassVerifier:
    """Verifies critical rules against source pages to catch hallucinations."""

    def __init__(self, pages: List[Dict]):
        """
        Args:
            pages: List of {page: int, text: str} — the full PDF page texts
        """
        self.pages  = {p["page"]: p["text"] for p in pages}
        bedrock_token = os.getenv("AWS_BEARER_TOKEN_BEDROCK")
        
        if bedrock_token:
            self.provider = "bedrock"
            self.bedrock_token = bedrock_token
            self.model = "mistral.mixtral-8x7b-instruct-v0:1"
            logger.info(f"[TwoPassVerifier] Initialized with Bedrock model {self.model}")
        else:
            self.provider = "groq"
            self.client = OpenAI(
                api_key=settings.groq_api_key,
                base_url="https://api.groq.com/openai/v1",
            )
            self.model  = "meta-llama/llama-4-scout-17b-16e-instruct"
            logger.info(f"[TwoPassVerifier] Initialized with Groq model {self.model}")
            
        logger.info(f"[TwoPassVerifier] {len(self.pages)} pages loaded")

    def verify_critical_rules(self, rules: List[Dict]) -> List[Dict]:
        """
        Runs second-pass verification on CRITICAL and HIGH severity rules.
        Fixes wrong source clauses and wrong thresholds.
        LOW and MEDIUM rules pass through unchanged.
        
        Args:
            rules: List of extracted rules
            
        Returns:
            List of verified rules with updated confidence scores
        """
        verified   = []
        to_verify  = [r for r in rules if r.get("severity") in ["CRITICAL", "HIGH"]]
        passthrough = [r for r in rules if r.get("severity") in ["MEDIUM", "LOW"]]
        skip       = [r for r in rules if r.get("severity") not in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]]

        logger.info(f"[Verifier] Processing {len(rules)} rules | "
                   f"Verifying: {len(to_verify)} CRITICAL/HIGH | "
                   f"Pass-through: {len(passthrough)} MEDIUM/LOW | "
                   f"Skip: {len(skip)}")

        for i, rule in enumerate(to_verify):
            page_num  = rule.get("page_number", 0)
            page_text = self.pages.get(page_num, "")

            if not page_text:
                # Cannot verify — reduce confidence but keep rule
                rule["confidence_score"] = min(rule.get("confidence_score", 0.9) - 0.15, 0.75)
                rule["verification_status"] = "skipped_no_page"
                verified.append(rule)
                logger.debug(f"[Verifier] Rule {i+1}/{len(to_verify)}: "
                            f"no page text, confidence reduced to {rule['confidence_score']}")
                continue

            try:
                prompt = VERIFY_PROMPT.format(
                    rule_json=json.dumps(rule, indent=2),
                    page_number=page_num,
                    page_text=page_text[:3000],
                )
                
                if self.provider == "bedrock":
                    url = f"https://bedrock-runtime.us-east-1.amazonaws.com/model/{self.model}/invoke"
                    headers = {
                        "Authorization": f"Bearer {self.bedrock_token}",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "prompt": f"<s>[INST] {prompt} [/INST]",
                        "max_tokens": 1024,
                        "temperature": 0.1,
                    }
                    try:
                        resp = requests.post(url, headers=headers, json=payload, timeout=45.0)
                        if resp.status_code >= 400:
                            logger.error(f"[Verifier] Bedrock {resp.status_code}: {resp.text}")
                            resp.raise_for_status()
                        raw = resp.json().get('outputs', [{}])[0].get('text', '{}')
                    except Exception as e:
                        logger.error(f"[Verifier] Bedrock request failed: {e}")
                        raw = "{}"
                else:
                    resp = self.client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.0,
                        max_tokens=512,
                        response_format={"type": "json_object"},
                    )
                    raw = resp.choices[0].message.content or "{}"
                
                # Strip markdown code fences if model wraps JSON in them
                if "```" in raw:
                    import re
                    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
                    raw = match.group(1).strip() if match else raw

                try:
                    result = json_repair.loads(raw) if isinstance(raw, str) else raw
                except Exception as e:
                    logger.error(f"[Verifier] Failed to repair JSON: {e}")
                    result = {}

                if result.get("source_clause_found") and result.get("thresholds_correct"):
                    # Rule verified successfully
                    if result.get("verified_source_clause"):
                        rule["source_clause"] = result["verified_source_clause"]
                    rule["needs_review"] = False
                    rule["verification_status"] = "verified"
                    rule["confidence_score"] = min(1.0, rule.get("confidence_score", 0.9) + 0.05)
                    logger.debug(f"[Verifier] Rule {i+1}/{len(to_verify)}: VERIFIED")

                elif result.get("correction_needed"):
                    # Rule has an error
                    rule["needs_review"] = True
                    rule["verification_status"] = "correction_needed"
                    rule["confidence_score"] = 0.5
                    rule["review_note"] = result["correction_needed"]
                    logger.warning(f"[Verifier] Rule {i+1}/{len(to_verify)}: "
                                  f"NEEDS CORRECTION: {rule.get('title')}")

                else:
                    # Source clause not found — likely hallucinated
                    rule["needs_review"] = True
                    rule["verification_status"] = "source_not_found"
                    rule["confidence_score"] = 0.3
                    rule["is_active"] = False
                    logger.warning(f"[Verifier] Rule {i+1}/{len(to_verify)}: "
                                  f"SOURCE NOT FOUND: {rule.get('title')}")

            except json.JSONDecodeError as e:
                logger.error(f"[Verifier] JSON decode error for rule {i+1}: {e}")
                rule["verification_status"] = "error_parse"
                rule["confidence_score"] = max(0.3, rule.get("confidence_score", 0.5) - 0.2)
                verified.append(rule)
                continue
                
            except Exception as e:
                logger.error(f"[Verifier] Error verifying rule {i+1} '{rule.get('title')}': {e}")
                rule["verification_status"] = "error_verify"
                rule["confidence_score"] = max(0.3, rule.get("confidence_score", 0.5) - 0.2)
                verified.append(rule)
                continue

            verified.append(rule)

        # Compile final results
        all_rules = verified + passthrough + skip
        approved  = sum(1 for r in all_rules if not r.get("needs_review", False))
        
        logger.info(f"[Verifier] Done. {approved}/{len(all_rules)} rules verified clean. "
                   f"Summary: {sum(1 for r in verified if r.get('verification_status') == 'verified')} verified, "
                   f"{sum(1 for r in verified if r.get('needs_review'))} need review")
        
        return all_rules

    def get_verification_stats(self, rules: List[Dict]) -> Dict:
        """Get statistics about verification results."""
        statuses = {}
        for rule in rules:
            status = rule.get("verification_status", "unknown")
            statuses[status] = statuses.get(status, 0) + 1
        
        return {
            "total_rules": len(rules),
            "statuses": statuses,
            "needs_review": sum(1 for r in rules if r.get("needs_review")),
            "avg_confidence": sum(r.get("confidence_score", 0.5) for r in rules) / len(rules) if rules else 0,
        }
