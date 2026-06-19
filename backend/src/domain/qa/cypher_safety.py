"""Pure Cypher validation and sanitization for VietMedKG read queries."""

from __future__ import annotations

import re

ALLOWED_NODE_LABELS = {"Disease", "Symptom", "Treatment", "Medicine", "Advice"}
ALLOWED_RELATIONSHIP_TYPES = {
    "HAS_SYMPTOM",
    "HAS_TREATMENT",
    "IS_PRESCRIBED",
    "HAS_ADVICE",
    "IS_LINKED_WITH",
}
DESTRUCTIVE_KEYWORDS = [
    r"\bDELETE\b",
    r"\bDROP\b",
    r"\bCREATE\b",
    r"\bSET\b",
    r"\bREMOVE\b",
    r"\bMERGE\b",
    r"\bDETACH\b",
    r"\bCALL\b",
    r"\bLOAD\s+CSV\b",
    r"\bFOREACH\b",
]


def validate_cypher(cypher: str) -> tuple[bool, str | None]:
    """Validate read-only Cypher syntax against the VietMedKG schema."""
    if not cypher or not cypher.strip():
        return False, "Cypher query is empty."

    for pattern in DESTRUCTIVE_KEYWORDS:
        match = re.search(pattern, cypher, re.IGNORECASE)
        if match:
            return False, f"Destructive command '{match.group()}' is not allowed."

    cypher_upper = cypher.upper().strip()
    if not re.search(r"\bMATCH\b", cypher_upper):
        return False, "Cypher query must contain a MATCH clause."
    if not re.search(r"\bRETURN\b", cypher_upper) and not re.search(r"\bWITH\b", cypher_upper):
        return False, "Cypher query must contain a RETURN or WITH clause."

    found_labels = set(re.findall(r"\(\s*\w*\s*:\s*([A-Z][a-zA-Z]*)", cypher))
    invalid_labels = found_labels - ALLOWED_NODE_LABELS - ALLOWED_RELATIONSHIP_TYPES
    if invalid_labels:
        return (
            False,
            "Unknown label(s) in query: "
            f"{', '.join(sorted(invalid_labels))}. "
            f"Allowed: {', '.join(sorted(ALLOWED_NODE_LABELS))}.",
        )

    found_rels = set(re.findall(r"\[\s*\w*\s*:\s*([A-Z_]+)\s*\]", cypher))
    invalid_rels = found_rels - ALLOWED_RELATIONSHIP_TYPES
    if invalid_rels:
        return (
            False,
            "Unknown relationship type(s): "
            f"{', '.join(sorted(invalid_rels))}. "
            f"Allowed: {', '.join(sorted(ALLOWED_RELATIONSHIP_TYPES))}.",
        )

    return True, None


def sanitize_cypher(cypher: str) -> str:
    """Block destructive Cypher before it reaches graph infrastructure."""
    is_valid, error = validate_cypher(cypher)
    if not is_valid:
        raise ValueError(error or "Invalid Cypher query.")
    return cypher
