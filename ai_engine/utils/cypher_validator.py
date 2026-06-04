"""Cypher Validator — Kiểm tra syntax và schema compliance."""

import re
import logging

logger = logging.getLogger(__name__)

# VietMedKG schema v2 — allowed labels and relationships
ALLOWED_NODE_LABELS = {"Disease", "Symptom", "Treatment", "Medicine", "Advice"}
ALLOWED_RELATIONSHIP_TYPES = {
    "HAS_SYMPTOM", "HAS_TREATMENT", "IS_PRESCRIBED", "HAS_ADVICE", "IS_LINKED_WITH"
}

# Destructive commands that must be blocked
DESTRUCTIVE_KEYWORDS = [
    r"\bDELETE\b", r"\bDROP\b", r"\bCREATE\b", r"\bSET\b",
    r"\bREMOVE\b", r"\bMERGE\b", r"\bDETACH\b", r"\bCALL\b",
    r"\bLOAD\s+CSV\b", r"\bFOREACH\b",
]


def validate_cypher(cypher: str) -> tuple[bool, str | None]:
    """Validate a Cypher query for syntax, schema compliance, and safety.

    Args:
        cypher: The Cypher query string to validate.

    Returns:
        Tuple of (is_valid, error_message).
        If valid: (True, None)
        If invalid: (False, "description of the issue")
    """
    if not cypher or not cypher.strip():
        return False, "Cypher query is empty."

    cypher_upper = cypher.upper().strip()

    # 1. Check for destructive commands
    for pattern in DESTRUCTIVE_KEYWORDS:
        if re.search(pattern, cypher, re.IGNORECASE):
            keyword = re.search(pattern, cypher, re.IGNORECASE).group()
            logger.warning("Destructive command detected: '%s'", keyword)
            return False, f"Destructive command '{keyword}' is not allowed."

    # 2. Basic syntax check — must contain MATCH and RETURN (or WITH)
    has_match = bool(re.search(r"\bMATCH\b", cypher_upper))
    has_return = bool(re.search(r"\bRETURN\b", cypher_upper))
    has_with = bool(re.search(r"\bWITH\b", cypher_upper))

    if not has_match:
        return False, "Cypher query must contain a MATCH clause."
    if not has_return and not has_with:
        return False, "Cypher query must contain a RETURN or WITH clause."

    # 3. Schema compliance — check node labels
    # Extract labels like (n:Label) or (:Label)
    found_labels = set(re.findall(r"\(\s*\w*\s*:\s*([A-Z][a-zA-Z]*)", cypher))
    # Filter out relationship types and property keys
    invalid_labels = found_labels - ALLOWED_NODE_LABELS - ALLOWED_RELATIONSHIP_TYPES
    if invalid_labels:
        return False, f"Unknown label(s) in query: {', '.join(sorted(invalid_labels))}. Allowed: {', '.join(sorted(ALLOWED_NODE_LABELS))}."

    # 4. Schema compliance — check relationship types
    # Extract relationship types like [:REL_TYPE] or -[:REL_TYPE]-
    found_rels = set(re.findall(r"\[\s*\w*\s*:\s*([A-Z_]+)\s*\]", cypher))
    invalid_rels = found_rels - ALLOWED_RELATIONSHIP_TYPES
    if invalid_rels:
        return False, f"Unknown relationship type(s): {', '.join(sorted(invalid_rels))}. Allowed: {', '.join(sorted(ALLOWED_RELATIONSHIP_TYPES))}."

    logger.debug("Cypher validation passed: labels=%s, rels=%s", found_labels, found_rels)
    return True, None
