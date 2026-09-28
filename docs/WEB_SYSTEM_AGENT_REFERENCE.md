# GeoAI Explorer — Agent, RAG, and Reasoning Reference

## What the “agent” is

The GeoAI agent is an orchestrator around deterministic intent parsing, canonical class resolution, GIS tools, local evidence retrieval, and response formatting. In the current live runtime it is **not powered by an external LLM**. The optional OpenAI component can only propose structured intent and is currently disabled.

## Current query path

```text
user query
 -> deterministic router
 -> mode: knowledge | spatial | mixed
 -> class aliases + relation/distance/area extraction
 -> canonical validation
 -> GIS repository and/or local RAG
 -> answer + result features + map actions + trace + limitations
```

Examples:

- `แหล่งน้ำ` → R4 class search.
- `สิ่งปลูกสร้าง` → R1 class search.
- `พื้นที่เกษตรใกล้น้ำ 300 เมตร` → R2 source, R4 target, near relation, 300 m.
- `R2 คืออะไร` → knowledge retrieval.

Unknown classes or missing required distances produce clarification rather than invented execution.

## Optional OpenAI planner

Activation requires both `OPENAI_API_KEY` and `AGENT_LLM_ENABLED=1`. Default configured model name is `gpt-5.6-terra`.

Safety boundary:

- Uses the Responses API for structured intent only.
- Sends no database rows and asks for no GIS facts.
- Uses `store:false` and a maximum output budget of 1,000 tokens.
- Cannot issue or execute SQL.
- Output is validated against R1–R7, relation allowlists, supported area units, distance ≤100 km, and bounded area values.
- Any failure returns to deterministic routing.

At audit time: key not configured, feature disabled, no paid call performed.

## Local RAG

RAG reads `backend/knowledge/knowledge_base.json`. Retrieval is lexical token overlap with rule-based boosts and `top_k` limited to 10. It has no embedding model, vector database, or generative answer requirement.

Curated topics include model identity, the Revised-7 taxonomy, R2 meaning, Full-AOI status, TEST40 limitations, and research interpretation cautions. The retrieval result supplies source/evidence text and category metadata.

## GIS tools

| Tool capability | Active repository behavior |
|---|---|
| class search | filter canonical class; optional bbox/geometry; paginate |
| near search | source features within maximum distance of target class |
| feature detail | attributes and centroid |
| GeoJSON fetch | selected feature geometries |
| identify | point-in-polygon / raster class identification |
| area/distance/intersection | projected EPSG:32647 operations |
| spectral evidence | NDVI/NDWI masked statistics |

Current repository is GeoPackage/GeoPandas/Shapely. The same contract has a parameterized read-only PostGIS implementation, but it is not active.

## Trace and reliability

The response can expose deterministic steps such as intent parsing, class resolution, spatial repository selection, GIS execution, and response construction. A trace explains which tools ran; it does not prove correctness by itself.

Fixed VAL4 references:

| Class | IoU | F1 |
|---|---:|---:|
| R1 | 0.653720 | 0.790578 |
| R2 | 0.548300 | 0.707615 |
| R3 | 0.719136 | 0.836568 |
| R4 | 0.617139 | 0.763043 |
| R5 | 0.309281 | 0.472383 |
| R6 | 0.215788 | 0.354909 |
| R7 | no fixed VAL4 support | no fixed VAL4 support |

These are class-level validation metrics. They are not local probability, polygon-level confidence, Full-AOI Ground Truth validation, or a guarantee for a user-drawn AOI.

## Search-result behavior

- The map remains satellite-first.
- Result geometry uses the canonical color of its class, not a universal green.
- All returned polygons can be drawn while labels are decluttered into numbered markers.
- Sidebar cards are paginated; clicking a card flies to and highlights its polygon.
- Only the active result gets a detailed popup.
- A class-only Full-AOI query may show every pixel of the class through a filtered categorical raster while returning polygon detail in pages.

## Known duplication

The repository contains:

1. Legacy `/api/agent`, `/api/search`, and tile-ranking/evidence tools.
2. Current `/api/agent/query` with V2 spatial/RAG contracts.

The current Explore result experience uses V2. Legacy routes remain for compatibility and tests. The older `/api/health` field `agent_enabled:true` reflects route availability, while `/api/system/integration-status` correctly reports the external LLM disabled. Advisor demonstrations should use the latter to describe runtime state.

## Evaluation status

- Agent V2, dry-run benchmark/scoring, and mocked LLM/PostGIS bridge tests passed in the audited 43-test suite.
- No paid LLM call was made by this audit.
- A dry run validates mechanics and scoring code, not model quality or provider selection.
- A planned 90-call paid pilot must remain explicitly labeled “not run” until executed and archived with prompts, responses, latency, token usage, cost, scores, and failures.

## Safe claims

Use: “The current system converts natural-language intent into validated deterministic GIS operations, with an optional disabled LLM planner.”

Do not use: “The LLM queries the database,” “the AI generates SQL,” “PostGIS is active,” “the result is Ground Truth,” or “the 90-call benchmark has passed.”
