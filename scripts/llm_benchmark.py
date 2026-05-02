"""LLM benchmark for KlinikAsistan dahiliye anamnez generation.

Runs the same transcript through multiple LLM providers and measures:
- Latency (total + p50/p95 across runs)
- JSON parse success rate
- 26-field completeness
- Format compliance (+, ----, ///, numeric-only fields)
- Output token count + estimated cost

Outputs:
  - bench_results/<timestamp>_raw.csv         (per-run rows)
  - bench_results/<timestamp>_summary.md      (markdown table for thesis)
  - bench_results/<timestamp>_summary.csv     (aggregated per-LLM)

Usage:
  # Single LLM, smoke test
  python scripts/llm_benchmark.py --llm haiku --transcripts bench_data/ --n-runs 3

  # All three providers
  python scripts/llm_benchmark.py --llm all --transcripts bench_data/ --n-runs 10

Providers:
  haiku  → Anthropic Claude Haiku 4.5 (claude-haiku-4-5-20251001)
  kimi   → Kimi K2 via OpenRouter (moonshotai/kimi-k2-0905)
  gemma  → Gemma via local Ollama (gemma2:9b by default)

Each provider uses its own system + user prompt:
  haiku/gemma → SYSTEM_PROMPT + ReportGenerator._build_dahiliye_prompt
  kimi        → SYSTEM_PROMPT_KIMI + USER_PROMPT_TEMPLATE_KIMI
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import statistics
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

# --- Project imports (require running from project root with venv active) ----
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.backend.src.prompts.section_prompts import (  # noqa: E402
    NUMERIC_FIELDS, OPTIONAL_FIELDS, get_anamnesis_sections,
)
from apps.backend.src.prompts.system_prompt import SYSTEM_PROMPT  # noqa: E402
from apps.backend.src.prompts.system_prompt_kimi import (  # noqa: E402
    SYSTEM_PROMPT_KIMI, USER_PROMPT_TEMPLATE_KIMI,
)
from apps.backend.src.services.report_generator import ReportGenerator  # noqa: E402

# ----------------------------------------------------------------------------
# Pricing (USD per 1M tokens) — UPDATE IF PRICES CHANGE
# ----------------------------------------------------------------------------
PRICING: dict[str, dict[str, float]] = {
    "haiku": {"input": 1.00, "output": 5.00},   # Claude Haiku 4.5
    "kimi":  {"input": 0.60, "output": 2.50},   # Kimi K2 via Moonshot direct
    "gemma": {"input": 0.0,  "output": 0.0},    # local
}

# ----------------------------------------------------------------------------
# Provider factory — reuses existing services
# ----------------------------------------------------------------------------
async def build_provider(name: str):
    if name == "haiku":
        from apps.backend.src.services.anthropic_service import AnthropicLLMService
        provider = AnthropicLLMService(model="claude-haiku-4-5-20251001")
    elif name == "kimi":
        from apps.backend.src.services.openrouter_service import OpenRouterLLMService
        provider = OpenRouterLLMService(model="moonshotai/kimi-k2-0905")
    elif name == "gemma":
        from apps.backend.src.services.llm_service import OllamaLLMService
        provider = OllamaLLMService(model="gemma2:9b")
    else:
        raise ValueError(f"Unknown provider: {name}")
    await provider.initialize()
    return provider


def _build_prompt_for(llm_name: str, transcript: str) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) tailored to the given provider."""
    if llm_name == "kimi":
        user_prompt = USER_PROMPT_TEMPLATE_KIMI.format(
            transcript=transcript, entities="(yok)"
        )
        return SYSTEM_PROMPT_KIMI, user_prompt
    user_prompt = ReportGenerator._build_dahiliye_prompt(transcript, [])
    return SYSTEM_PROMPT, user_prompt


# ----------------------------------------------------------------------------
# Per-run measurement
# ----------------------------------------------------------------------------
@dataclass
class RunResult:
    llm: str
    case_id: str
    run_idx: int
    total_ms: float
    json_ok: bool
    field_count: int           # how many of the 26 keys are present
    field_present_pct: float   # field_count / 26
    field_filled_pct: float    # non-empty, non-BELIRTILMEDI / 26
    format_ok_pct: float       # 0..1, ratio of fields that pass format checks
    numeric_violations: int    # alpha chars in numeric-only fields
    output_chars: int
    error: str = ""


def _check_format(parsed: dict[str, str]) -> tuple[float, int]:
    """Return (format_ok_ratio, numeric_violations).

    Heuristic checks the LLM-violatable rules:
    - All non-numeric, non-empty values uppercase
    - NUMERIC_FIELDS contain digits only (optional decimal point)
    """
    if not parsed:
        return 0.0, 0
    ok = 0
    total = 0
    numeric_violations = 0
    for key, val in parsed.items():
        val = (val or "").strip()
        total += 1
        if key in NUMERIC_FIELDS:
            if val == "" or re.fullmatch(r"\d+([.,]\d+)?", val):
                ok += 1
            else:
                numeric_violations += 1
        else:
            # uppercase rule (Turkish letters allowed)
            if val == "" or val == "BELIRTILMEDI":
                ok += 1
            elif val == val.upper():
                ok += 1
    return (ok / total) if total else 0.0, numeric_violations


def _filled_count(parsed: dict[str, str]) -> int:
    sentinels = {"", "BELIRTILMEDI", "BELIRTILMEDI."}
    return sum(1 for v in parsed.values() if (v or "").strip() not in sentinels)


async def run_once(
    provider, transcript: str, expected_keys: list[str],
    llm_name: str, case_id: str, run_idx: int,
) -> RunResult:
    """Single transcript → single LLM call → parsed metrics."""
    system_prompt, user_prompt = _build_prompt_for(llm_name, transcript)
    t0 = time.perf_counter()
    err = ""
    raw = ""
    try:
        raw = await provider.generate(user_prompt, system_prompt)
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    total_ms = (time.perf_counter() - t0) * 1000

    parsed: dict[str, str] = {}
    if raw:
        parsed = ReportGenerator._parse_batch_response(raw, expected_keys)

    json_ok = bool(parsed)
    field_count = sum(1 for k in expected_keys if k in parsed)
    fmt_ratio, num_viol = _check_format(parsed)

    return RunResult(
        llm=llm_name,
        case_id=case_id,
        run_idx=run_idx,
        total_ms=total_ms,
        json_ok=json_ok,
        field_count=field_count,
        field_present_pct=field_count / len(expected_keys) if expected_keys else 0.0,
        field_filled_pct=_filled_count(parsed) / len(expected_keys) if expected_keys else 0.0,
        format_ok_pct=fmt_ratio,
        numeric_violations=num_viol,
        output_chars=len(raw),
        error=err,
    )


# ----------------------------------------------------------------------------
# Aggregation
# ----------------------------------------------------------------------------
@dataclass
class LLMSummary:
    llm: str
    n_runs: int
    n_cases: int
    latency_p50: float
    latency_p95: float
    json_success_pct: float        # %
    field_present_avg_pct: float   # %
    field_filled_avg_pct: float    # %
    format_ok_avg_pct: float       # %
    numeric_violations_total: int
    avg_output_chars: float
    estimated_cost_per_1k_calls_usd: float
    error_count: int


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def aggregate(results: list[RunResult]) -> dict[str, LLMSummary]:
    by_llm: dict[str, list[RunResult]] = {}
    for r in results:
        by_llm.setdefault(r.llm, []).append(r)

    summaries: dict[str, LLMSummary] = {}
    for llm, rows in by_llm.items():
        latencies = [r.total_ms for r in rows if not r.error]
        ok_rows = [r for r in rows if r.json_ok]
        cases = {r.case_id for r in rows}
        # Cost: rough estimate, output_chars / 4 ≈ tokens (Turkish; coarse)
        avg_out_chars = statistics.mean(r.output_chars for r in rows) if rows else 0
        avg_out_tokens = avg_out_chars / 4
        # Input cost is dominated by the prompt template (~3500 tokens) + transcript
        avg_in_tokens = 4000  # rough constant for the dahiliye prompt
        price = PRICING.get(llm, {"input": 0.0, "output": 0.0})
        per_call = (avg_in_tokens * price["input"] + avg_out_tokens * price["output"]) / 1_000_000
        cost_per_1k = per_call * 1000

        summaries[llm] = LLMSummary(
            llm=llm,
            n_runs=len(rows),
            n_cases=len(cases),
            latency_p50=_percentile(latencies, 0.50),
            latency_p95=_percentile(latencies, 0.95),
            json_success_pct=100 * len(ok_rows) / len(rows) if rows else 0.0,
            field_present_avg_pct=100 * statistics.mean(r.field_present_pct for r in ok_rows) if ok_rows else 0.0,
            field_filled_avg_pct=100 * statistics.mean(r.field_filled_pct for r in ok_rows) if ok_rows else 0.0,
            format_ok_avg_pct=100 * statistics.mean(r.format_ok_pct for r in ok_rows) if ok_rows else 0.0,
            numeric_violations_total=sum(r.numeric_violations for r in ok_rows),
            avg_output_chars=avg_out_chars,
            estimated_cost_per_1k_calls_usd=cost_per_1k,
            error_count=sum(1 for r in rows if r.error),
        )
    return summaries


# ----------------------------------------------------------------------------
# Output writers
# ----------------------------------------------------------------------------
def write_raw_csv(path: Path, results: list[RunResult]) -> None:
    if not results:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        for r in results:
            writer.writerow(asdict(r))


def write_summary_csv(path: Path, summaries: dict[str, LLMSummary]) -> None:
    if not summaries:
        return
    rows = list(summaries.values())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for s in rows:
            writer.writerow(asdict(s))


def write_summary_md(path: Path, summaries: dict[str, LLMSummary], n_runs: int) -> None:
    """Markdown table copy-pasteable into the thesis."""
    if not summaries:
        return
    order = ["haiku", "kimi", "gemma"]
    cols = [llm for llm in order if llm in summaries]

    def cell(llm: str, fmt: str) -> str:
        s = summaries[llm]
        return fmt.format(s=s)

    lines = [
        f"# LLM Benchmark Sonuçları",
        f"_n={n_runs} run/case, {next(iter(summaries.values())).n_cases} case_",
        "",
        "| Metrik | " + " | ".join(c.upper() for c in cols) + " |",
        "|---|" + "---|" * len(cols),
    ]

    metrics = [
        ("Latency p50 (ms)",        "{s.latency_p50:.0f}"),
        ("Latency p95 (ms)",        "{s.latency_p95:.0f}"),
        ("JSON parse success (%)",  "{s.json_success_pct:.1f}"),
        ("26 alan tam (%)",         "{s.field_present_avg_pct:.1f}"),
        ("Alan dolu (%) ",          "{s.field_filled_avg_pct:.1f}"),
        ("Format compliance (%)",   "{s.format_ok_avg_pct:.1f}"),
        ("Numeric ihlal (toplam)",  "{s.numeric_violations_total}"),
        ("Ortalama çıktı (karakter)","{s.avg_output_chars:.0f}"),
        ("Cost / 1000 çağrı (USD)", "${s.estimated_cost_per_1k_calls_usd:.3f}"),
        ("Hata sayısı",             "{s.error_count}"),
    ]
    for label, fmt in metrics:
        cells = [cell(llm, fmt) for llm in cols]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")

    path.write_text("\n".join(lines), encoding="utf-8")


# ----------------------------------------------------------------------------
# Main runner
# ----------------------------------------------------------------------------
async def benchmark(
    llm_names: list[str],
    transcript_files: list[Path],
    n_runs: int,
    out_dir: Path,
) -> None:
    expected_keys = list(get_anamnesis_sections("dahiliye").keys())
    transcripts = [(f.stem, f.read_text(encoding="utf-8")) for f in transcript_files]

    all_results: list[RunResult] = []
    for llm_name in llm_names:
        print(f"\n=== {llm_name.upper()} ===")
        try:
            provider = await build_provider(llm_name)
        except Exception as e:  # noqa: BLE001
            print(f"  FAIL build: {e}")
            continue
        try:
            for case_id, transcript in transcripts:
                for run_idx in range(n_runs):
                    r = await run_once(
                        provider, transcript, expected_keys,
                        llm_name, case_id, run_idx,
                    )
                    all_results.append(r)
                    status = "OK" if r.json_ok else "FAIL"
                    err = f" err={r.error}" if r.error else ""
                    print(f"  {case_id} run#{run_idx}: {r.total_ms:6.0f}ms "
                          f"json={status} fields={r.field_count}/26{err}")
        finally:
            try:
                await provider.shutdown()
            except Exception:  # noqa: BLE001
                pass

    summaries = aggregate(all_results)

    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    write_raw_csv(out_dir / f"{ts}_raw.csv", all_results)
    write_summary_csv(out_dir / f"{ts}_summary.csv", summaries)
    write_summary_md(out_dir / f"{ts}_summary.md", summaries, n_runs)

    print(f"\nSonuçlar yazıldı:\n  {out_dir / (ts + '_raw.csv')}")
    print(f"  {out_dir / (ts + '_summary.csv')}")
    print(f"  {out_dir / (ts + '_summary.md')}\n")
    print((out_dir / f"{ts}_summary.md").read_text())


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--llm", choices=["haiku", "kimi", "gemma", "all"], required=True)
    p.add_argument("--transcripts", type=Path, required=True,
                   help="Dizin: her .txt bir test transkripti")
    p.add_argument("--n-runs", type=int, default=3,
                   help="Vaka başına run sayısı (latency varyans için)")
    p.add_argument("--out", type=Path,
                   default=Path(__file__).resolve().parents[1] / "bench_results")
    args = p.parse_args()

    if not args.transcripts.is_dir():
        sys.exit(f"transkript dizini bulunamadi: {args.transcripts}")
    files = sorted(args.transcripts.glob("*.txt"))
    if not files:
        sys.exit(f"{args.transcripts} icinde .txt yok")

    targets = ["haiku", "kimi", "gemma"] if args.llm == "all" else [args.llm]
    asyncio.run(benchmark(targets, files, args.n_runs, args.out))


if __name__ == "__main__":
    main()
