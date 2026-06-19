"""Neo4j Graph Repository Adapter — implements IGraphRepository.

Wraps the neo4j AsyncDriver to provide Knowledge Graph operations
against VietMedKG (Neo4j AuraDB).

Key design decisions:
- Uses AsyncDriver for async/await throughout.
- Connection is created lazily on first query.
- find_diseases_by_name() uses CONTAINS for partial matching
  (mirrors the legacy graph_service.py query pattern).
"""

from __future__ import annotations

import logging
from typing import Any

from ports.graph import IGraphRepository

logger = logging.getLogger(__name__)


class Neo4jGraphRepository(IGraphRepository):
    """Production adapter for IGraphRepository backed by Neo4j AuraDB.

    Args:
        uri: The bolt/neo4j+s:// URI.
        username: Neo4j username (default 'neo4j').
        password: Neo4j password.
    """

    def __init__(self, uri: str, username: str, password: str) -> None:
        self._uri = uri
        self._username = username
        self._password = password
        self._driver = None

    def _get_driver(self):
        """Lazily create the async driver on first use."""
        if self._driver is None:
            try:
                from neo4j import AsyncGraphDatabase
            except ImportError as exc:
                raise ImportError(
                    "neo4j driver not installed. Run: pip install neo4j"
                ) from exc
            self._driver = AsyncGraphDatabase.driver(
                self._uri,
                auth=(self._username, self._password),
            )
            logger.info("Neo4jGraphRepository: driver created (uri=%s)", self._uri[:40])
        return self._driver

    async def execute_cypher(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a Cypher query and return results as list of dicts."""
        driver = self._get_driver()
        try:
            async with driver.session() as session:
                result = await session.run(query, parameters=params or {})
                records = await result.data()
                logger.debug(
                    "execute_cypher: %d records (query=%s…)",
                    len(records),
                    query[:60],
                )
                return records
        except Exception as exc:
            from domain.shared.errors import InfrastructureError
            raise InfrastructureError(f"Neo4j query failed: {exc}") from exc

    async def find_diseases_by_name(
        self, name: str, *, limit: int = 30
    ) -> list[str]:
        """Find diseases whose name contains the given substring (case-insensitive)."""
        cypher = """
        MATCH (d:Disease)
        WHERE toLower(d.disease_name) CONTAINS toLower($name)
        RETURN d.disease_name AS disease_name
        LIMIT $limit
        """
        try:
            records = await self.execute_cypher(cypher, {"name": name, "limit": limit})
            return [r["disease_name"] for r in records if r.get("disease_name")]
        except Exception as exc:
            logger.warning("find_diseases_by_name failed for '%s': %s", name, exc)
            return []

    async def get_disease_detail(self, disease_name: str) -> dict[str, Any] | None:
        """Fetch full details for a disease by exact name."""
        cypher = """
        MATCH (d:Disease {disease_name: $name})
        OPTIONAL MATCH (d)-[:HAS_SYMPTOM]->(s:Symptom)
        OPTIONAL MATCH (d)-[:HAS_TREATMENT]->(t:Treatment)
        OPTIONAL MATCH (d)-[:HAS_MEDICINE]->(m:Medicine)
        OPTIONAL MATCH (d)-[:HAS_ADVICE]->(a:Advice)
        RETURN
            d.disease_name AS disease_name,
            d.description AS description,
            d.disease_category AS disease_category,
            collect(DISTINCT s.name) AS symptoms,
            collect(DISTINCT t.name) AS treatments,
            collect(DISTINCT m.name) AS medicines,
            collect(DISTINCT a.name) AS advice
        """
        try:
            records = await self.execute_cypher(cypher, {"name": disease_name})
            return records[0] if records else None
        except Exception as exc:
            logger.warning("get_disease_detail failed for '%s': %s", disease_name, exc)
            return None

    async def get_schema_info(self) -> dict[str, Any]:
        """Return the graph schema (node labels, relationship types, counts)."""
        try:
            node_cypher = """
            CALL db.labels() YIELD label
            CALL apoc.cypher.run('MATCH (n:' + label + ') RETURN count(n) AS count', {})
            YIELD value
            RETURN label, value.count AS count
            """
            rel_cypher = "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType"

            try:
                nodes = await self.execute_cypher(node_cypher)
                rels = await self.execute_cypher(rel_cypher)
            except Exception:
                # Fallback if APOC not available
                nodes = await self.execute_cypher(
                    "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count"
                )
                rels = await self.execute_cypher(
                    "MATCH ()-[r]->() RETURN DISTINCT type(r) AS relationshipType"
                )

            return {
                "nodes": [{"label": r.get("label"), "count": r.get("count", 0)} for r in nodes],
                "relationships": [
                    {"type": r.get("relationshipType")} for r in rels
                ],
            }
        except Exception as exc:
            logger.warning("get_schema_info failed: %s", exc)
            return {"nodes": [], "relationships": [], "error": str(exc)}

    async def check_connectivity(self) -> bool:
        """Check if the graph database is reachable."""
        try:
            driver = self._get_driver()
            await driver.verify_connectivity()
            return True
        except Exception as exc:
            logger.warning("Neo4j connectivity check failed: %s", exc)
            return False

    async def close(self) -> None:
        """Release the database connection/driver."""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4jGraphRepository: driver closed")
