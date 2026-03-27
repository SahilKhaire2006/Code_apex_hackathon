"""
Layer 8: Dedup + Confidence Validator
Removes duplicate rules and auto-approves high-confidence extractions.
Rules with confidence >= 0.85 are auto-approved, others flagged for review.
"""

from typing import List, Dict, Tuple
from difflib import SequenceMatcher
from core.logger import logger


CONFIDENCE_THRESHOLD_AUTO_APPROVE = 0.85


def are_rules_similar(rule1: Dict, rule2: Dict, threshold: float = 0.8) -> bool:
    """
    Check if two rules are similar (potential duplicates).
    
    Args:
        rule1: First rule dict
        rule2: Second rule dict
        threshold: Similarity threshold (0-1)
        
    Returns:
        True if rules are likely duplicates
    """
    # Compare titles
    title1 = rule1.get("title", "").lower().strip()
    title2 = rule2.get("title", "").lower().strip()
    
    if not title1 or not title2:
        return False
    
    title_ratio = SequenceMatcher(None, title1, title2).ratio()
    
    # Compare severity and type
    same_severity = rule1.get("severity") == rule2.get("severity")
    same_type = rule1.get("rule_type") == rule2.get("rule_type")
    
    # Rules are duplicates if titles are similar AND severity/type match
    if title_ratio >= threshold and same_severity and same_type:
        return True
    
    # Also check descriptions for very high similarity
    if title_ratio >= 0.95:
        desc1 = rule1.get("description", "").lower().strip()
        desc2 = rule2.get("description", "").lower().strip()
        
        if desc1 and desc2:
            desc_ratio = SequenceMatcher(None, desc1, desc2).ratio()
            if desc_ratio >= threshold:
                return True
    
    return False


def deduplicate_rules(rules: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """
    Remove duplicate rules, keeping the one with higher confidence score.
    
    Args:
        rules: List of extracted rules
        
    Returns:
        (deduplicated_rules, removed_duplicates)
    """
    if not rules:
        return [], []
    
    deduped = []
    removed = []
    seen_indices = set()
    
    for i, rule1 in enumerate(rules):
        if i in seen_indices:
            continue
        
        best_rule = rule1
        best_idx = i
        
        # Find any duplicates of this rule
        for j, rule2 in enumerate(rules[i+1:], start=i+1):
            if j in seen_indices:
                continue
            
            if are_rules_similar(rule1, rule2):
                # Keep the one with higher confidence
                rule2_confidence = rule2.get("confidence_score", 0.5)
                best_confidence = best_rule.get("confidence_score", 0.5)
                
                if rule2_confidence > best_confidence:
                    removed.append(best_rule)
                    best_rule = rule2
                    best_idx = j
                else:
                    removed.append(rule2)
                
                seen_indices.add(j)
        
        deduped.append(best_rule)
        seen_indices.add(best_idx)
    
    logger.info(f"[Deduplicator] {len(rules)} rules → {len(deduped)} after dedup "
               f"({len(removed)} duplicates removed)")
    
    return deduped, removed


def apply_confidence_validation(rules: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """
    Auto-approve rules with confidence >= threshold, flag others for review.
    
    Args:
        rules: List of rules from verification stage
        
    Returns:
        (auto_approved_rules, flagged_for_review)
    """
    auto_approved = []
    flagged = []
    
    for rule in rules:
        confidence = rule.get("confidence_score", 0.5)
        
        if confidence >= CONFIDENCE_THRESHOLD_AUTO_APPROVE and not rule.get("needs_review"):
            rule["is_approved"] = True
            rule["approval_status"] = "auto_approved"
            auto_approved.append(rule)
        else:
            rule["is_approved"] = False
            rule["approval_status"] = "pending_review"
            flagged.append(rule)
    
    auto_rate = (len(auto_approved) / len(rules) * 100) if rules else 0
    logger.info(f"[ConfidenceValidator] {len(rules)} rules | "
               f"Auto-approved: {len(auto_approved)} ({auto_rate:.0f}%) | "
               f"Flagged: {len(flagged)}")
    
    return auto_approved, flagged


def validate_rule_structure(rule: Dict) -> Tuple[bool, List[str]]:
    """
    Validate that a rule has all required fields.
    
    Args:
        rule: Rule dict to validate
        
    Returns:
        (is_valid, list_of_errors)
    """
    required_fields = ["title", "description", "severity"]
    optional_fields = ["source_clause", "rule_type", "page_number", "confidence_score"]
    
    errors = []
    
    # Check required fields
    for field in required_fields:
        if field not in rule or not rule[field]:
            errors.append(f"Missing required field: {field}")
    
    # Check severity is valid
    if rule.get("severity") not in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        errors.append(f"Invalid severity: {rule.get('severity')}")
    
    # Check confidence is in valid range
    if rule.get("confidence_score") is not None:
        conf = rule.get("confidence_score")
        if not (0 <= conf <= 1):
            errors.append(f"Confidence score out of range: {conf}")
    
    # Check description length
    desc = rule.get("description", "")
    if len(desc) < 20:
        errors.append(f"Description too short ({len(desc)} chars < 20)")
    elif len(desc) > 5000:
        errors.append(f"Description too long ({len(desc)} chars > 5000)")
    
    is_valid = len(errors) == 0
    return is_valid, errors


def filter_valid_rules(rules: List[Dict]) -> Tuple[List[Dict], List[Tuple[Dict, List[str]]]]:
    """
    Filter out invalid rules and collect validation errors.
    
    Args:
        rules: List of rule dicts
        
    Returns:
        (valid_rules, invalid_rules_with_errors)
    """
    valid = []
    invalid = []
    
    for rule in rules:
        is_valid, errors = validate_rule_structure(rule)
        if is_valid:
            valid.append(rule)
        else:
            invalid.append((rule, errors))
            for error in errors:
                logger.warning(f"[RuleValidator] Invalid rule '{rule.get('title')}': {error}")
    
    if invalid:
        logger.warning(f"[RuleValidator] {len(invalid)} rules failed validation")
    
    return valid, invalid


def get_dedup_stats(original_rules: List[Dict], deduped_rules: List[Dict]) -> Dict:
    """Get statistics about deduplication."""
    return {
        "original_count": len(original_rules),
        "final_count": len(deduped_rules),
        "duplicates_removed": len(original_rules) - len(deduped_rules),
        "dedup_ratio": round((len(original_rules) - len(deduped_rules)) / len(original_rules) * 100, 1) if original_rules else 0,
    }


def get_approval_stats(rules: List[Dict]) -> Dict:
    """Get statistics about auto-approval."""
    auto_approved = sum(1 for r in rules if r.get("is_approved"))
    return {
        "total": len(rules),
        "auto_approved": auto_approved,
        "pending_review": len(rules) - auto_approved,
        "auto_approve_rate": round(auto_approved / len(rules) * 100, 1) if rules else 0,
    }
