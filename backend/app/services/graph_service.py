"""Graph Service — Neo4j AuraDB connection & Cypher execution.

This service is retained for:
- GET /api/v1/schema endpoint (graph statistics)
- Direct Neo4j queries when needed (fallback)
- Health check for database connectivity
"""

import asyncio
import logging
from typing import Any

from neo4j import AsyncGraphDatabase

from app.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USERNAME

logger = logging.getLogger(__name__)

# ── Singleton driver ──────────────────────────────────────────────────────
_driver = None
_driver_lock = asyncio.Lock()


async def get_driver():
    """Get or create the Neo4j async driver singleton.

    Uses double-checked locking to ensure thread-safe initialization,
    consistent with lightrag_service.py singleton pattern.

    Returns:
        An async Neo4j driver instance.
    """
    global _driver
    if _driver is not None:
        return _driver
    async with _driver_lock:
        # Double-check after acquiring lock
        if _driver is None:
            _driver = AsyncGraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
            )
            logger.info("Neo4j driver created for: %s", NEO4J_URI)
    return _driver


async def execute_cypher(query: str, parameters: dict | None = None) -> list[dict[str, Any]]:
    """Execute a Cypher query and return results as list of dicts.

    Args:
        query: The Cypher query to execute.
        parameters: Optional query parameters.

    Returns:
        List of record dictionaries.
    """
    driver = await get_driver()

    async with driver.session() as session:
        result = await session.run(query, parameters or {})
        records = await result.data()
        logger.debug("Cypher executed: %d records returned.", len(records))
        return records


async def check_connectivity() -> bool:
    """Check if the Neo4j database is reachable.

    Returns:
        True if connected successfully.
    """
    try:
        driver = await get_driver()
        await driver.verify_connectivity()
        return True
    except Exception as e:
        logger.error("Neo4j connectivity check failed: %s", e)
        return False


async def get_schema_info() -> dict[str, Any]:
    """Get graph schema information from Neo4j.

    Returns:
        Dict with node labels, relationship types, and counts.
    """
    try:
        # APOC not available in AuraDB — using simpler db.labels() query.
        # N+1 pattern intentional here: called only by /schema health endpoint,
        # not in the hot query path.
        node_query_simple = """
        CALL db.labels() YIELD label
        RETURN label
        """

        labels = await execute_cypher(node_query_simple)

        nodes = []
        for row in labels:
            label = row["label"]
            count_result = await execute_cypher(
                f"MATCH (n:`{label}`) RETURN count(n) AS count"
            )
            count = count_result[0]["count"] if count_result else 0

            # Get properties for this label
            props_result = await execute_cypher(
                f"MATCH (n:`{label}`) WITH n LIMIT 1 RETURN keys(n) AS props"
            )
            props = props_result[0]["props"] if props_result else []

            nodes.append({"label": label, "count": count, "properties": props})

        # Get relationship types
        rel_query = "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType"
        rel_types = await execute_cypher(rel_query)

        relationships = []
        for row in rel_types:
            rel_type = row["relationshipType"]
            count_result = await execute_cypher(
                f"MATCH ()-[r:`{rel_type}`]->() RETURN count(r) AS count"
            )
            count = count_result[0]["count"] if count_result else 0
            relationships.append({"type": rel_type, "count": count})

        return {"nodes": nodes, "relationships": relationships}

    except Exception as e:
        logger.error("Failed to get schema info: %s", e)
        return {"nodes": [], "relationships": [], "error": str(e)}


async def close_driver() -> None:
    """Close the Neo4j driver connection."""
    global _driver
    if _driver:
        await _driver.close()
        _driver = None
        logger.info("Neo4j driver closed.")
