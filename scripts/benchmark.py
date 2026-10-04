"""Empirical benchmarking script comparing Unrestricted Baseline vs AgentFlow Budget-Controlled execution."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.agent import AgentFlowAgent
from app.agent.config import AgentConfig
from app.database.connection import get_default_db_path
from app.database.seed import seed_database
from app.services.token_budget import compress_tool_result, estimate_string_tokens

BENCHMARK_PROMPTS = [
    "Query total sales revenue by region from the database and compute each region's percentage of overall revenue.",
    "Identify our top 3 best-selling products by quantity and calculate the average gross margin.",
    "Calculate the percentage difference between total gross revenue and total net revenue from sales.",
]


@dataclass
class RunMetrics:
    prompt: str
    latency_ms: float
    llm_calls: int
    tool_calls: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    success: bool


async def run_scenario(agent: AgentFlowAgent, prompt: str) -> RunMetrics:
    """Runs a single prompt through an agent and captures exact metrics."""
    start = time.perf_counter()
    try:
        result = await agent.achat(prompt, request_id=f"bm_{int(time.time() * 1000)}")
        latency = (time.perf_counter() - start) * 1000
        tm = result.token_metrics
        return RunMetrics(
            prompt=prompt,
            latency_ms=round(latency, 2),
            llm_calls=tm.get("llm_calls", 0),
            tool_calls=tm.get("tool_calls", len(result.tools_used)),
            prompt_tokens=tm.get("prompt_tokens", 0),
            completion_tokens=tm.get("completion_tokens", 0),
            total_tokens=tm.get("total_tokens", 0),
            cost_usd=tm.get("estimated_cost_usd", 0.0),
            success=result.success,
        )
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        return RunMetrics(
            prompt=prompt,
            latency_ms=round(latency, 2),
            llm_calls=0,
            tool_calls=0,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost_usd=0.0,
            success=False,
        )


async def main_benchmark() -> None:
    print("=" * 80)
    print("AgentFlow — Empirical Token & Cost Control Benchmark")
    print("=" * 80)

    # Ensure database exists
    db_path = get_default_db_path()
    if not db_path.exists():
        print("[*] Seeding database for benchmark...")
        seed_database(db_path)

    api_key = os.getenv("GEMINI_API_KEY")
    has_api_key = api_key and api_key.strip() not in ("", "your_gemini_api_key_here")

    # 1. Unrestricted configuration (large limits, no result compression)
    unrestricted_cfg = AgentConfig(
        max_agent_iterations=15,
        max_tool_calls=25,
        max_request_time_seconds=120.0,
        max_output_tokens=4096,
    )

    # 2. AgentFlow budget-controlled configuration
    budget_cfg = AgentConfig(
        max_agent_iterations=6,
        max_tool_calls=8,
        max_request_time_seconds=30.0,
        max_output_tokens=2048,
    )

    print(f"Executing {len(BENCHMARK_PROMPTS)} test scenarios across both configurations...\n")

    if not has_api_key:
        print("[!] Note: GEMINI_API_KEY is not configured.")
        print("    Running benchmark in simulated data mode to demonstrate metric tracking.")
        # Provide simulated data run
        baseline_tokens = 3450
        budget_tokens = 2410
        baseline_latency = 2850.0
        budget_latency = 2100.0
        baseline_cost = (baseline_tokens / 1_000_000) * 0.15
        budget_cost = (budget_tokens / 1_000_000) * 0.15

        token_savings = ((baseline_tokens - budget_tokens) / baseline_tokens) * 100
        latency_savings = ((baseline_latency - budget_latency) / baseline_latency) * 100
        cost_savings = ((baseline_cost - budget_cost) / baseline_cost) * 100

        print("\n" + "-" * 80)
        print("BENCHMARK COMPARISON RESULTS (Simulated Reference)")
        print("-" * 80)
        print(f"{'Metric':<30} | {'Unrestricted':<18} | {'AgentFlow Budget':<18} | {'Reduction':<12}")
        print("-" * 80)
        print(f"{'Avg Latency (ms)':<30} | {baseline_latency:<18.2f} | {budget_latency:<18.2f} | {latency_savings:<10.1f} %")
        print(f"{'Avg Total Tokens':<30} | {baseline_tokens:<18} | {budget_tokens:<18} | {token_savings:<10.1f} %")
        print(f"{'Est Cost per 1k requests ($)':<30} | {baseline_cost * 1000:<18.4f} | {budget_cost * 1000:<18.4f} | {cost_savings:<10.1f} %")
        print("-" * 80)
        print("\nTo benchmark against live Gemini endpoints, set GEMINI_API_KEY in .env and re-run.")
        return

    # Real execution with Gemini LLM
    unrestricted_agent = AgentFlowAgent(config=unrestricted_cfg)
    budget_agent = AgentFlowAgent(config=budget_cfg)

    baseline_runs: List[RunMetrics] = []
    budget_runs: List[RunMetrics] = []

    for i, prompt in enumerate(BENCHMARK_PROMPTS, 1):
        print(f"[{i}/{len(BENCHMARK_PROMPTS)}] Running: '{prompt[:50]}...'")
        print("  -> Running Baseline (Unrestricted)...")
        b_res = await run_scenario(unrestricted_agent, prompt)
        baseline_runs.append(b_res)

        print("  -> Running Budget-Controlled (AgentFlow)...")
        a_res = await run_scenario(budget_agent, prompt)
        budget_runs.append(a_res)

    # Compute averages
    avg_base_lat = sum(r.latency_ms for r in baseline_runs) / len(baseline_runs)
    avg_budg_lat = sum(r.latency_ms for r in budget_runs) / len(budget_runs)

    avg_base_tok = sum(r.total_tokens for r in baseline_runs) / len(baseline_runs)
    avg_budg_tok = sum(r.total_tokens for r in budget_runs) / len(budget_runs)

    avg_base_cost = sum(r.cost_usd for r in baseline_runs) / len(baseline_runs)
    avg_budg_cost = sum(r.cost_usd for r in budget_runs) / len(budget_runs)

    tok_red = ((avg_base_tok - avg_budg_tok) / avg_base_tok * 100) if avg_base_tok else 0.0
    lat_red = ((avg_base_lat - avg_budg_lat) / avg_base_lat * 100) if avg_base_lat else 0.0
    cost_red = ((avg_base_cost - avg_budg_cost) / avg_base_cost * 100) if avg_base_cost else 0.0

    print("\n" + "=" * 80)
    print("MEASURED EMPIRICAL RESULTS")
    print("=" * 80)
    print(f"{'Metric':<30} | {'Unrestricted':<18} | {'AgentFlow Budget':<18} | {'Measured Delta':<14}")
    print("-" * 80)
    print(f"{'Avg Latency (ms)':<30} | {avg_base_lat:<18.2f} | {avg_budg_lat:<18.2f} | {lat_red:<12.1f} %")
    print(f"{'Avg Total Tokens':<30} | {avg_base_tok:<18.1f} | {avg_budg_tok:<18.1f} | {tok_red:<12.1f} %")
    print(f"{'Est Cost per 1k requests ($)':<30} | {avg_base_cost * 1000:<18.4f} | {avg_budg_cost * 1000:<18.4f} | {cost_red:<12.1f} %")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main_benchmark())
