# LLM Orchestrator Benchmark Methodology V1

## Research objective

This benchmark evaluates LLMs as orchestration layers for the existing Semantic-Spatial Search system. It does not evaluate segmentation accuracy or GIS correctness. GIS logic, A7-T, Revised 7-class taxonomy, RAG knowledge and the tool contract remain fixed.

## Controlled design

Every provider receives the same locked system prompt, canonical schema, tool definitions, query and structured-output constraints. Provider-specific syntax is normalized by adapters. Gold answers are stored in `benchmarks/agent_benchmark_v1.json`, marked `created_before_provider_runs=true`, and are never included in provider prompts.

The benchmark has 30 Thai queries: six each for spatial, knowledge, mixed, ambiguous and unsupported behavior. The three predefined candidates, selection date, and six inclusion criteria are locked in `benchmarks/model_selection_v1.json` (2026-09-16). Each query is run three independent times. Requests omit `temperature`, `top_p`, `top_k`, and unsupported `seed`, using each model's provider default. The adapters report `seed_supported=false`; consistency is measured across the three repeats, not by emulated seed control. Run metadata records the requested sampling policy and provider-reported model ID, but labels opaque actual provider defaults as unknown.

## Two-phase orchestration

1. Provider returns a structured plan: mode, canonical classes, explicit parameters, clarification/unsupported state, GIS tool calls and RAG requests.
2. The harness executes allow-listed GIS tools and project RAG outside the LLM.
3. When verified results exist, the provider receives those results for a grounded final response.

This ordering prevents an answer from being counted as grounded merely because it mentions a tool.

## Metrics

- **Intent Accuracy:** exact spatial/knowledge/mixed classification.
- **Class Resolution Accuracy:** field-level accuracy for class/source/target/parent class.
- **Parameter Extraction Score:** partial credit per explicit distance, area, unit or relation field.
- **Tool Selection Accuracy:** required-tool coverage with a penalty for unnecessary tools.
- **Clarification Accuracy:** correct clarification and no premature GIS execution.
- **Unsupported Handling Accuracy:** explicit limitation, no forbidden capability claim and no unsupported GIS execution.
- **Grounding Rate:** successful GIS execution for spatial, project-RAG retrieval for knowledge, and both for mixed requests. Clarification/unsupported cases are excluded from this denominator.
- **Consistency Rate:** dominant identical normalized orchestration signature across repeated runs.
- **Latency:** total, provider and tool execution latency; summary reports median and P95 total latency.
- **Cost:** provider-reported token usage multiplied by external `provider_pricing.json`; missing pricing or usage yields null, not an estimate. Cached-token cost is also null when a provider-specific cache rate is unavailable, rather than assumed equal to standard input.

No automatic composite score is produced.
Unsupported Handling Accuracy is aggregated over the six unsupported queries only; routine supported queries cannot inflate the safety score.

## Selection gate

Required predefined thresholds:

- Intent Accuracy >= 0.95
- Tool Selection Accuracy >= 0.95
- Unsupported Handling Accuracy = 1.00
- Grounding Rate >= 0.90

Passing models are reported as eligible candidates. The code does not auto-select a winner. If none passes, the report states `NO_CANDIDATE_MET_ALL_THRESHOLDS`. Latency and cost remain separate decision dimensions.
The gate is evaluable only after all 30 queries complete at least three error-free runs each. Filtered or interrupted runs cannot pass it.

## Contamination controls

- Gold answers, expected tools and category labels are scorer-only data.
- Provider prompts contain only the shared system instruction and user query.
- Prompt SHA-256, dataset SHA-256 and tool-contract SHA-256 are recorded.
- Any future gold edit requires a benchmark version bump and documented reason.

## Limitations

- Thirty project-specific queries do not represent all geospatial-agent behavior.
- Provider defaults and determinism vary; the benchmark does not force common sampling parameters.
- Provider-native token accounting and cache definitions differ.
- Latency depends on network/provider load and local GIS execution.
- Benchmark scores assess orchestration, not land-cover truth or polygon accuracy.
