import json
import time
from typing import List
from langchain_groq import ChatGroq
from core.config import settings
from core.logger import logger
from core.schemas import Rule


SYSTEM_PROMPT = """You are a financial compliance rule extraction specialist working on the RBI Master Circular on KYC/AML Guidelines (DNBS(PD) CC No.231/03.10.42/2011-12 dated July 1, 2011).

════════════════════════════════════════════════════════════
STEP 1 — DECIDE IF THIS CHUNK IS EXTRACTABLE
════════════════════════════════════════════════════════════

SKIP this chunk entirely and return {"rules": []} if it is:
- A form with fields to fill in (PART 1, PART 2, PART 3 sections of CCR/CTR/STR forms)
- A data structure table defining file formats (CCRCTL.txt, CCRBRC.txt field definitions)
- An illustration or calculation example (like Annex-I cash transaction illustration)
- An appendix that only lists circular numbers and dates
- A cover letter or forwarding paragraph with no obligations
- A section that only references obligations already stated elsewhere with no new conditions

EXTRACT from this chunk if it contains:
- Words like "must", "shall", "should", "are required to", "are advised to", "are directed to"
- Specific thresholds (amounts in rupees, time limits in days/years, frequencies)
- Prohibitions ("must not", "shall not", "should not allow", "not permitted")
- Conditional obligations ("in the event of", "where", "if", "when")

════════════════════════════════════════════════════════════
STEP 2 — EXTRACT EACH RULE WITH ALL REQUIRED FIELDS
════════════════════════════════════════════════════════════

For each actionable obligation, extract ONE rule JSON object with ALL fields below.

title: Maximum 8 words. A noun phrase. E.g., "Cash Transaction Reporting Threshold".

category: MUST be exactly one of: KYC, AML, REPORTING, PEP, CFT, PMLA, FATF, RECORD_KEEPING, TRANSACTION_THRESHOLD, EMPLOYEE_CONDUCT

severity:
  CRITICAL → Direct PMLA/RBI Act violation. Penalties possible.
  HIGH     → Regulatory action likely if violated.
  MEDIUM   → Internal control failure.
  LOW      → Best practice not followed.

logic_type: REQUIRED | PROHIBITED | CONDITIONAL | THRESHOLD

page_number: Integer. The PDF page number provided in the USER message.

paragraph_number: E.g., "Para 18", "Para 21(b)", "Annex-VI Para 4". Use nearest heading if not explicit.

act_section: E.g., "Section 12 of PMLA 2002", "Rule 3 of PMLA Rules 2005". If not cited, use: "Master Circular DNBS(PD) CC No.231/03.10.42/2011-12 dated July 1, 2011"

circular_reference: Most specific RBI circular credited. If none, use: "DNBS(PD) CC No.231/03.10.42/2011-12 dated July 1, 2011"

source_clause: VERBATIM copy of 1-3 sentences that state the obligation. Do NOT paraphrase.

description: 1-2 sentence technical summary. Third person. Present tense.

plain_english: MUST start with "This means:". 2-3 simple sentences explaining trigger, action, consequence.

violation_message_template: Template string using {placeholders}. Available: {transaction_id}, {transaction_date}, {transaction_type}, {amount}, {account_id}, {customer_id}, {customer_name}, {country}, {days_overdue}, {flag_date}, {record_age_years}, {pep_flag}, {kyc_status}, {monthly_cash_total}, {threshold_value}

applicable_entity: NBFC | RNBC | ALL

metadata_tags: Array of 2-5 from: PMLA, STR, CTR, CCR, FIU-IND, FATF, KYC, AML, PEP, CFT, RBI, RECORD-KEEPING, THRESHOLD, SANCTIONS, UNSCR, UN-LIST, CASH, IDENTITY-VERIFICATION, DUE-DILIGENCE, PRINCIPAL-OFFICER, RNBC, HIGH-RISK-COUNTRY, CORRESPONDENT-BANKING, WIRE-TRANSFER, BENEFICIAL-OWNER

condition_field: One of: amount, monthly_cash_total, transaction_type, country, kyc_status, account_age_days, customer_risk_category, pep_flag, record_age_years, cash_transaction_count, sanctions_list_match, str_filed, days_since_suspicious_flag. Null for REQUIRED/PROHIBITED.

condition_operator: gt | gte | lt | lte | eq | neq | in | not_in | missing | contains. Null if no condition.

condition_value: Numeric string without commas. Rs.10 lakh = "1000000". Null if no condition.

condition_unit: INR | USD | days | years | months | count | boolean | category | country_code | percentage. Null if no condition.

confidence_score: Float 0.0-1.0.
  1.0  = Explicit threshold + specific act section + paragraph number
  0.95 = Explicit threshold + act section, no paragraph
  0.90 = Clear obligation + paragraph reference, no act section
  0.85 = Clear obligation, inferred, no specific references
  0.70 = Implied obligation, some ambiguity
  Below 0.70 = DO NOT EXTRACT.

════════════════════════════════════════════════════════════
STEP 3 — DEDUPLICATION CHECK BEFORE RETURNING
════════════════════════════════════════════════════════════

Skip rules that ONLY restate an earlier circular with no new threshold, deadline, or condition.
Merge rules that say the same thing into one.

════════════════════════════════════════════════════════════
OUTPUT FORMAT — STRICTLY FOLLOW THIS
════════════════════════════════════════════════════════════

Return ONLY valid JSON. No markdown code fences. No explanation.

{"rules": [{"title": "...", "category": "...", "severity": "...", "logic_type": "...", "page_number": 0, "paragraph_number": "...", "act_section": "...", "circular_reference": "...", "source_clause": "...", "description": "...", "plain_english": "...", "violation_message_template": "...", "applicable_entity": "...", "metadata_tags": ["..."], "condition_field": null, "condition_operator": null, "condition_value": null, "condition_unit": null, "confidence_score": 0.0}]}

If no extractable rules exist, return exactly: {"rules": []}
"""


class RuleExtractionAgent:
    """
    Extracts structured compliance rules from policy text chunks using Groq LLM.
    Implements the full 19-field RBI KYC/AML rule extraction specification.
    """

    def __init__(self):
        self.llm = ChatGroq(
            groq_api_key=settings.groq_api_key,
            model_name="meta-llama/llama-4-scout-17b-16e-instruct",
            temperature=0
        )
        logger.info("RuleExtractionAgent initialized with Groq (Llama 3.3 70B)")

    def _parse_response(self, content: str) -> list:
        """Strip markdown fences and parse JSON from LLM response."""
        content = content.strip()
        if content.startswith("```"):
            # Remove ```json ... ``` or ``` ... ```
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]).strip()
        return json.loads(content)

    def extract_rules(self, text: str, page_number: int = 0, max_retries: int = 2) -> List[Rule]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"PDF Page: {page_number}\n\nChunk Text:\n{text}"}
        ]

        logger.info(f"Extracting rules from page {page_number} ({len(text)} chars)")

        for attempt in range(max_retries + 1):
            try:
                response = self.llm.invoke(messages)
                content = response.content

                if not content or not content.strip():
                    raise ValueError("LLM returned empty response")

                parsed = self._parse_response(content)
                raw_rules = parsed.get("rules", [])

                rules = []
                for r in raw_rules:
                    if r.get("confidence_score", 0) < 0.70:
                        continue
                    try:
                        rules.append(Rule(**r))
                    except Exception as e:
                        logger.warning(f"Skipping malformed rule: {e}")

                logger.info(f"Extracted {len(rules)} rules from page {page_number}")
                return rules

            except (json.JSONDecodeError, ValueError) as e:
                if attempt < max_retries:
                    wait = 2 ** attempt  # 1s, 2s backoff
                    logger.warning(f"Page {page_number} parse error (attempt {attempt+1}): {e}. Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    logger.error(f"JSON parse error on page {page_number} after {max_retries+1} attempts: {e}")
                    return []
            except Exception as e:
                logger.error(f"Unexpected error on page {page_number}: {e}")
                return []
        return []
