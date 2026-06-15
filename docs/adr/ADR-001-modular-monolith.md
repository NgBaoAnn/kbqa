# ADR-001: Adopt Modular Monolith with Clean Architecture

**Status:** Accepted
**Date:** 2026-06-15
**Decision Makers:** @NgBaoAn

## Context

The KBQA (AegisHealth) project is a Medical QA system using Hybrid GraphRAG
(Cypher queries on Neo4j + LightRAG with Qdrant). The codebase has grown
organically across `backend/`, `ai_engine/`, `etl/`, and `frontend/` modules
with several architectural issues:

1. **Config duplication**: Neo4j credentials declared in both `backend/config.py`
   and `ai_engine/config.py`.
2. **Pipeline God Object**: `pipeline.py` (596 lines) mixes routing, entity
   disambiguation, Cypher path, and LightRAG path.
3. **Cross-module coupling**: `pipeline.py` directly imports 5+ modules from
   `ai_engine`, making isolated testing impossible.
4. **No domain layer**: Business logic (safety, source normalization) lives
   directly in service classes with no pure entities or value objects.
5. **No interface/port abstraction**: Swapping infrastructure (e.g., replacing
   Neo4j or LightRAG) requires changing business logic.

## Decision

We will refactor the codebase to a **Modular Monolith** with **Clean Architecture**
(Hexagonal/Ports & Adapters) boundaries.

### Why Modular Monolith (not Microservices)

| Criterion | Microservices | Modular Monolith ✅ |
|-----------|---------------|---------------------|
| Team size (1-3) | Excessive overhead | Right-sized |
| AI Engine latency | +5-50ms network hop | ~0ms in-process |
| Deployment | K8s/Docker Compose | Single process |
| Data consistency | Eventual consistency | Single transaction |
| Future migration | — | Easy to split later |

### Architecture Layers

```
Adapters (infra) → Ports (interfaces) ← Domain (pure logic)
                                       ← Use Cases (orchestration)
API Gateway (routers) → Use Cases
```

**Dependency Rule**: Dependencies point inward only. Domain has zero external
dependencies.

### Key Decisions

- **Q1**: Split `contracts.py` into `requests.py`, `responses.py`, `internal.py`
- **Q2**: Extract prompt templates into `src/prompts/*.md` files
- **Q3**: Merge `etl/` + `scripts/ingest_to_neo4j.py` into `data_pipeline/`
- **Q4**: Add Zustand for frontend state management
- **Q5**: Write in-memory adapters for all 4 ports (Graph, Vector, DB, LLM) in Phase 2
- **Q6**: Migrate `pyproject.toml` to standard `src` layout

## Consequences

### Positive
- Domain logic testable without infrastructure (Neo4j, Qdrant, Supabase)
- Single config source eliminates credential duplication
- Infrastructure swappable via port interfaces
- Codebase is AI-navigable with clear naming conventions
- Future microservice extraction is straightforward

### Negative
- More files (~60 → ~90 Python files)
- Port interface boilerplate
- Team learning curve for dependency rules
- 6-phase incremental refactoring effort (~10-14 working days)

### Risks
- Over-engineering for a 1-3 person team (mitigated by applying Clean Arch
  only at important boundaries, not full DDD tactical patterns)

## References

- [Clean Architecture (Robert C. Martin)](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [Hexagonal Architecture (Alistair Cockburn)](https://alistair.cockburn.us/hexagonal-architecture/)
- [Modular Monolith (Kamil Grzybek)](https://www.kamilgrzybek.com/blog/posts/modular-monolith-primer)
- KBQA Architecture Blueprint: `implementation_plan.md`
