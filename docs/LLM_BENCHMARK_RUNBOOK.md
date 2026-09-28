# LLM Benchmark Runbook

## 1. Locked candidates and keys

Candidates are locked as of 2026-09-16 in `benchmarks/model_selection_v1.json`: `gpt-5.6-terra`, `gemini-3.8-flash`, and `claude-sonnet-5`. The CLI refuses a different `--model`. Configure only the key for the provider being run:

```powershell
$env:OPENAI_API_KEY = "..."
$env:GEMINI_API_KEY = "..."
$env:ANTHROPIC_API_KEY = "..."
```

Do not write keys into repository files. Verify account-level access and current rates before paid calls. Pricing is in `benchmarks/provider_pricing.json`; Gemini's configured rate expires after 2026-12-31. This preflight uses no paid API calls and therefore cannot prove account entitlement or live endpoint compatibility.

Requests omit `temperature`, `top_p`, `top_k`, and seed. Provider defaults are intentionally used; run records capture what was sent and whether the provider reported an actual model ID. Opaque provider sampling defaults remain marked unknown. Formal runs require exactly three repeats.

## 2. Dry-run

Dry-run validates dataset/schema/prompt/tool contract and shows missing configuration. It makes zero API calls.

```powershell
Set-Location D:\499_2\semantic_search_app
C:\Users\Admin\anaconda3\envs\geoai\python.exe benchmarks\run_benchmark.py --dry-run
```

Filter validation without API cost:

```powershell
C:\Users\Admin\anaconda3\envs\geoai\python.exe benchmarks\run_benchmark.py --provider openai --query-id S01 --runs 3 --dry-run
C:\Users\Admin\anaconda3\envs\geoai\python.exe benchmarks\run_benchmark.py --category spatial --dry-run
```

## 3. Run one provider

Run only after explicit authorization for paid calls and verified provider credentials. The model selection is already locked.

```powershell
C:\Users\Admin\anaconda3\envs\geoai\python.exe benchmarks\run_benchmark.py --provider openai --runs 3
C:\Users\Admin\anaconda3\envs\geoai\python.exe benchmarks\run_benchmark.py --provider gemini --runs 3
C:\Users\Admin\anaconda3\envs\geoai\python.exe benchmarks\run_benchmark.py --provider anthropic --runs 3
```

Assert the locked model for one provider (other IDs are refused):

```powershell
C:\Users\Admin\anaconda3\envs\geoai\python.exe benchmarks\run_benchmark.py --provider openai --model "gpt-5.6-terra" --runs 3
```

## 4. Run all configured providers

```powershell
C:\Users\Admin\anaconda3\envs\geoai\python.exe benchmarks\run_benchmark.py --provider all --runs 3
```

## 5. Resume after failure

Use one explicit raw JSONL path so completed `(query_id, run_id)` pairs can be skipped.

```powershell
C:\Users\Admin\anaconda3\envs\geoai\python.exe benchmarks\run_benchmark.py --provider openai --runs 3 --output benchmarks\results\raw\openai_selected_model.jsonl
C:\Users\Admin\anaconda3\envs\geoai\python.exe benchmarks\run_benchmark.py --provider openai --runs 3 --output benchmarks\results\raw\openai_selected_model.jsonl --resume
```

## 6. Outputs

- Raw per-run records: `benchmarks/results/raw/*.jsonl`
- Summary JSON: `benchmarks/results/summary/benchmark_summary.json`
- Summary CSV: `benchmarks/results/summary/benchmark_summary.csv`
- Dry-run report: `benchmarks/results/summary/dry_run_report.json`

Every raw record contains gold data for the scorer, normalized provider output, score breakdown, execution trace summary, latency, usage, cost when pricing exists, and failures. Gold data is written only after the provider response; it is never sent to the provider.
