"""CLI interactive runner for AgentFlow (`python -m app`)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from app.agent.agent import AgentFlowAgent
from app.database.connection import get_default_db_path
from app.database.seed import seed_database


def run_cli() -> None:
    """Runs AgentFlow in terminal CLI mode."""
    print("=" * 70)
    print("AgentFlow — Autonomous Multi-Tool AI Agent (CLI Mode)")
    print("=" * 70)

    # 1. Verify database exists
    db_path = get_default_db_path()
    if not db_path.exists():
        print(f"[*] Database not found at {db_path}. Seeding sample business database...")
        seed_database(db_path)
        print("[+] Database seeded successfully.")

    # 2. Check API key
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key.strip() in ("", "your_gemini_api_key_here"):
        print("\n[!] WARNING: GEMINI_API_KEY is not set.")
        print("    Please set GEMINI_API_KEY in your .env file to enable LLM reasoning.")
        print("    You can obtain an API key at https://aistudio.google.com/app/apikey\n")

    agent = AgentFlowAgent()

    # Check for single query argument passed via CLI
    if len(sys.argv) > 1:
        user_query = " ".join(sys.argv[1:])
        print(f"\nUser Query: {user_query}")
        print("-" * 70)
        try:
            result = agent.chat(user_query)
            print(f"\n[Final Answer]:\n{result.answer}\n")
            print(f"[Tools Used]: {', '.join(result.tools_used) or 'None (Direct Answer)'}")
            print(f"[Execution Time]: {result.execution_time_ms} ms")
            if result.trace:
                print("\n[Safe Execution Trace]:")
                for step in result.trace:
                    print(f"  Step {step['step_index']}: {step['tool_name']} ({step['execution_time_ms']}ms)")
                    print(f"    Input:  {step['input_summary']}")
                    print(f"    Result: {step['output_summary']}")
        except Exception as exc:
            print(f"[!] Error: {exc}")
        return

    # Interactive REPL mode
    print("Interactive session started. Enter your request, or type 'exit' or 'quit' to quit.\n")
    while True:
        try:
            user_input = input("AgentFlow > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("Exiting AgentFlow CLI. Goodbye!")
                break

            print("\nAgentFlow is reasoning and executing tools...")
            result = agent.chat(user_input)

            print(f"\n[Final Answer]:\n{result.answer}\n")
            print(f"[Tools Used]: {', '.join(result.tools_used) or 'None (Direct Answer)'}")
            print(f"[Execution Time]: {result.execution_time_ms} ms")

            if result.trace:
                print("\n[Safe Execution Trace]:")
                for step in result.trace:
                    print(f"  - Step {step['step_index']}: {step['tool_name']} [{step['status']}] ({step['execution_time_ms']}ms)")
                    print(f"    Input:  {step['input_summary']}")
                    print(f"    Result: {step['output_summary']}")
            print("-" * 70 + "\n")

        except KeyboardInterrupt:
            print("\nSession interrupted. Exiting.")
            break
        except Exception as exc:
            print(f"[!] Error: {exc}\n")


if __name__ == "__main__":
    run_cli()
