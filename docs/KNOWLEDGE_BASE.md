# Project knowledge base

The V2 knowledge source is `backend/knowledge/knowledge_base.json`. Retrieval is local, deterministic and dependency-light.

## Categories

1. `land_cover_taxonomy`: R1-R7 definitions, aliases and taxonomy limits.
2. `model_metadata`: frozen A7-T identity, U-Net architecture, PlanetScope RGBN order, Revised 7-class, Tversky loss and scratch training.
3. `validation_limitations`: Fixed VAL4 metrics/context, no Ground Truth for TEST40, and Full AOI prediction limitations.
4. `tool_api_documentation`: GIS tool purpose, units, deterministic boundary and spectral limitations.

Every document has an ID, category, title, content and provenance source. Retrieved content is evidence for explanations only; it never computes spatial results.

## Metric provenance

The aggregate and class-level A7-T values are sourced from `FINAL_TVERSKY_PROMOTION_AUDIT.json`. Frozen operational seed-42 identity is sourced from `D:/499_4/FINAL_MODEL_FREEZE/A7_RGBN_REVISED7_TVERSKY/`.

The per-class values originally supplied in the task matched the earlier A7 seed-42 artifact rather than frozen A7-T. To avoid cross-model mislabelling, the implemented KB uses the verified A7-T multi-seed class means from the promotion audit. R7 remains `no support`.

## Retrieval response

```json
{
  "documents": [
    {
      "id": "validation-a7t",
      "category": "validation_limitations",
      "title": "A7-T validation context and limitations",
      "content": "...",
      "source": "project knowledge base",
      "relevance_score": 1.0
    }
  ]
}
```
