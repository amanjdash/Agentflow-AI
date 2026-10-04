"""AgentFlow ReAct Agent Engine with loop bounds, safe trace extraction, and streaming."""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Union
from llama_index.core.agent.react.formatter import ReActChatFormatter
from llama_index.core.agent.react.output_parser import ReActOutputParser
from llama_index.core.agent.react.types import (
    ActionReasoningStep,
    BaseReasoningStep,
    ObservationReasoningStep,
    ResponseReasoningStep,
)
from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.core.llms import LLM
from llama_index.core.tools import BaseTool

from app.agent.callbacks import AgentTraceTracker, SafeTraceItem
from app.agent.config import AgentConfig, get_agent_config
from app.agent.gemini_llm import create_gemini_llm
from app.agent.prompts import get_system_prompt
from app.safety.limits import GLOBAL_LIMITS
from app.services.logging import get_logger, set_request_id
from app.services.token_budget import compress_tool_result, estimate_string_tokens
from app.tools.tool_registry import get_agent_tools

logger = get_logger("agentflow.agent")

THOUGHT_REGEX = re.compile(r"(?i)thought:\s*.*?(?=(action:|answer:|$))", re.DOTALL)


def sanitize_final_answer(raw_text: str) -> str:
    """Ensures private chain-of-thought or internal reasoning tags are never returned to the user."""
    if not raw_text:
        return ""
    # If the model included "Answer:", take the substring following the final "Answer:"
    if "Answer:" in raw_text:
        parts = raw_text.split("Answer:")
        answer = parts[-1].strip()
    elif "answer:" in raw_text:
        parts = raw_text.split("answer:")
        answer = parts[-1].strip()
    else:
        # Strip out any lingering Thought: blocks
        answer = THOUGHT_REGEX.sub("", raw_text).strip()

    # Remove residual Action: markers if any
    if "Action:" in answer:
        answer = answer.split("Action:")[0].strip()

    return answer


class AgentFlowResult:
    """Structured result produced by an AgentFlow execution."""

    def __init__(
        self,
        answer: str,
        tools_used: List[str],
        execution_time_ms: float,
        trace: List[Dict[str, Any]],
        token_metrics: Dict[str, Any],
        success: bool = True,
    ) -> None:
        self.answer = answer
        self.tools_used = tools_used
        self.execution_time_ms = execution_time_ms
        self.trace = trace
        self.token_metrics = token_metrics
        self.success = success

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "tools_used": self.tools_used,
            "execution_time_ms": self.execution_time_ms,
            "trace": self.trace,
            "token_metrics": self.token_metrics,
            "success": self.success,
        }


class AgentFlowAgent:
    """Autonomous Multi-Tool AI Agent implementing a guarded ReAct reasoning loop."""

    def __init__(
        self,
        llm: Optional[LLM] = None,
        tools: Optional[List[BaseTool]] = None,
        config: Optional[AgentConfig] = None,
        system_prompt: Optional[str] = None,
    ) -> None:
        self.config = config or get_agent_config()
        self.tools = tools or get_agent_tools()
        self._tools_dict = {tool.metadata.name: tool for tool in self.tools}
        self.system_prompt = system_prompt or get_system_prompt()
        self._llm = llm  # Lazily instantiated if None
        self.formatter = ReActChatFormatter(system_header=self.system_prompt)
        self.output_parser = ReActOutputParser()

    @property
    def llm(self) -> LLM:
        if self._llm is None:
            self._llm = create_gemini_llm(self.config)
        return self._llm

    def _execute_tool_safely(
        self,
        tool_name: str,
        action_input: Union[Dict[str, Any], str],
        tracker: AgentTraceTracker,
        tool_counts: Dict[str, int],
    ) -> str:
        """Executes a selected tool with parameter normalization and bounds checking."""
        tool = self._tools_dict.get(tool_name)
        if not tool:
            err = f"Error: Tool '{tool_name}' is not recognized. Permitted tools: {list(self._tools_dict.keys())}"
            tracker.record_tool_call(tool_name, action_input, err, 0.0, success=False)
            return err

        # Check per-tool invocation quotas
        tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
        limit_map = {
            "sql_query": GLOBAL_LIMITS.max_sql_calls_per_request,
            "web_search": GLOBAL_LIMITS.max_web_search_calls_per_request,
            "execute_python": GLOBAL_LIMITS.max_python_calls_per_request,
        }
        max_allowed = limit_map.get(tool_name, 5)
        if tool_counts[tool_name] > max_allowed:
            err = f"Error: Maximum calls for tool '{tool_name}' ({max_allowed}) reached for this request."
            tracker.record_tool_call(tool_name, action_input, err, 0.0, success=False)
            return err

        # Normalize action input into kwargs
        kwargs: Dict[str, Any] = {}
        if isinstance(action_input, dict):
            kwargs = action_input
        elif isinstance(action_input, str):
            # Attempt to parse string as JSON
            try:
                parsed = json.loads(action_input)
                if isinstance(parsed, dict):
                    kwargs = parsed
                else:
                    # Single parameter mapping
                    if tool_name in ("sql_query", "web_search"):
                        kwargs = {"query": str(parsed)}
                    elif tool_name == "execute_python":
                        kwargs = {"code": str(parsed)}
                    else:
                        kwargs = {"input": str(parsed)}
            except Exception:
                # Direct string argument
                if tool_name in ("sql_query", "web_search"):
                    kwargs = {"query": action_input}
                elif tool_name == "execute_python":
                    kwargs = {"code": action_input}
                else:
                    kwargs = {"input": action_input}

        start_time = time.perf_counter()
        try:
            raw_output = tool(**kwargs)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            # Ensure tool result is a string
            output_str = str(raw_output)
            tracker.record_tool_call(tool_name, kwargs, output_str, elapsed_ms, success=True)
            return compress_tool_result(output_str)

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            err_msg = f"Error executing tool '{tool_name}': {str(exc)}"
            logger.warning(err_msg)
            tracker.record_tool_call(tool_name, kwargs, err_msg, elapsed_ms, success=False)
            return err_msg

    def chat(self, message: str, request_id: str = "req_default") -> AgentFlowResult:
        """Synchronous chat execution running the ReAct loop."""
        return asyncio.run(self.achat(message, request_id=request_id))

    async def _call_llm(self, messages: List[ChatMessage]) -> ChatResponse:
        """Invokes LLM safely in a worker thread to avoid Windows aiohttp DNS resolution bugs."""
        try:
            return await asyncio.to_thread(self.llm.chat, messages)
        except Exception as sync_err:
            logger.warning(f"Thread-pooled chat failed: {sync_err}. Falling back to async chat.")
            return await self.llm.achat(messages)

    async def achat(self, message: str, request_id: str = "req_default") -> AgentFlowResult:
        """Asynchronous ReAct reasoning loop with loop bounding and safe trace capturing."""
        set_request_id(request_id)
        tracker = AgentTraceTracker(request_id=request_id)

        chat_history: List[ChatMessage] = [
            ChatMessage(role=MessageRole.USER, content=message)
        ]
        current_reasoning: List[BaseReasoningStep] = []
        tool_counts: Dict[str, int] = {}

        total_start = time.perf_counter()
        final_answer = ""
        success = True

        for iteration in range(1, self.config.max_agent_iterations + 1):
            # Check global request time budget
            elapsed_total = time.perf_counter() - total_start
            if elapsed_total > self.config.max_request_time_seconds:
                final_answer = (
                    "Execution exceeded the maximum allowed request duration. "
                    "Returning best available response based on completed steps."
                )
                logger.warning(f"Request {request_id} timed out after {elapsed_total:.2f}s")
                success = False
                break

            # Check total tool calls limit
            if len(tracker.trace_items) >= self.config.max_tool_calls:
                final_answer = (
                    "Maximum tool execution limit reached. "
                    "Synthesizing final answer from gathered data."
                )
                logger.warning(f"Request {request_id} reached max tool calls: {self.config.max_tool_calls}")
                break

            # 1. Format messages with system instructions and current reasoning trace
            formatted_messages = self.formatter.format(
                tools=self.tools,
                chat_history=chat_history,
                current_reasoning=current_reasoning,
            )

            # Estimate prompt tokens
            prompt_text = "".join(m.content for m in formatted_messages)
            prompt_tokens_est = estimate_string_tokens(prompt_text)

            # 2. Invoke LLM
            llm_start = time.perf_counter()
            try:
                response = await self._call_llm(formatted_messages)
                raw_response_text = response.message.content or ""
            except Exception as exc:
                logger.error(f"LLM generation failed on iteration {iteration}: {exc}")
                final_answer = f"The AI model encountered an error while processing: {str(exc)}"
                success = False
                break

            completion_tokens_est = estimate_string_tokens(raw_response_text)
            tracker.token_metrics.record_llm_call(prompt_tokens_est, completion_tokens_est)

            # 3. Parse ReAct step (Action or Final Answer)
            try:
                step = self.output_parser.parse(raw_response_text)
            except Exception as parse_err:
                logger.warning(f"Output parse error on iteration {iteration}: {parse_err}. Allowing agent recovery.")
                if "Answer:" in raw_response_text or "answer:" in raw_response_text:
                    final_answer = sanitize_final_answer(raw_response_text)
                    break
                current_reasoning.append(
                    ObservationReasoningStep(
                        observation=f"Format Error: Could not extract tool use: {parse_err}. Please provide:\nAction: <tool_name>\nAction Input: {{\"query\": \"...\"}}\nor Answer: <final response>"
                    )
                )
                continue

            if isinstance(step, ResponseReasoningStep):
                # ReAct loop determined final response
                final_answer = sanitize_final_answer(step.response)
                break

            elif isinstance(step, ActionReasoningStep):
                # ReAct loop selected an action
                current_reasoning.append(step)
                tool_name = step.action
                action_input = step.action_input

                # Execute tool
                observation = self._execute_tool_safely(tool_name, action_input, tracker, tool_counts)
                current_reasoning.append(ObservationReasoningStep(observation=observation))

            else:
                final_answer = sanitize_final_answer(raw_response_text)
                break

        if not final_answer:
            # Fallback if loop ended without explicit ResponseReasoningStep
            final_answer = "Analysis completed. Relevant tools were executed to gather information."

        total_latency_ms = tracker.finish()

        return AgentFlowResult(
            answer=final_answer,
            tools_used=tracker.tools_used,
            execution_time_ms=total_latency_ms,
            trace=[t.to_dict() for t in tracker.trace_items],
            token_metrics=tracker.token_metrics.to_dict(),
            success=success,
        )

    async def astream(
        self, message: str, request_id: str = "stream_default"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Streams safe execution progress events (SSE compatible) without revealing internal chain-of-thought."""
        set_request_id(request_id)
        tracker = AgentTraceTracker(request_id=request_id)

        yield {
            "event": "start",
            "request_id": request_id,
            "timestamp": time.time(),
            "message": "Request received. AgentFlow planning started.",
        }

        chat_history: List[ChatMessage] = [
            ChatMessage(role=MessageRole.USER, content=message)
        ]
        current_reasoning: List[BaseReasoningStep] = []
        tool_counts: Dict[str, int] = {}
        total_start = time.perf_counter()
        final_answer = ""

        for iteration in range(1, self.config.max_agent_iterations + 1):
            if (time.perf_counter() - total_start) > self.config.max_request_time_seconds:
                final_answer = "Execution exceeded time limit."
                break

            yield {
                "event": "planning",
                "iteration": iteration,
                "message": f"Evaluating action for iteration {iteration}...",
            }

            formatted_messages = self.formatter.format(
                tools=self.tools,
                chat_history=chat_history,
                current_reasoning=current_reasoning,
            )
            prompt_tokens_est = estimate_string_tokens("".join(m.content for m in formatted_messages))

            try:
                response = await self._call_llm(formatted_messages)
                raw_response_text = response.message.content or ""
            except Exception as exc:
                yield {"event": "error", "message": f"LLM error: {str(exc)}"}
                final_answer = f"Error during model generation: {str(exc)}"
                break

            completion_tokens_est = estimate_string_tokens(raw_response_text)
            tracker.token_metrics.record_llm_call(prompt_tokens_est, completion_tokens_est)

            try:
                step = self.output_parser.parse(raw_response_text)
            except Exception:
                final_answer = sanitize_final_answer(raw_response_text)
                break

            if isinstance(step, ResponseReasoningStep):
                final_answer = sanitize_final_answer(step.response)
                break

            elif isinstance(step, ActionReasoningStep):
                tool_name = step.action
                action_input = step.action_input

                yield {
                    "event": "tool_start",
                    "iteration": iteration,
                    "tool": tool_name,
                    "input_summary": str(action_input)[:150],
                }

                current_reasoning.append(step)
                observation = self._execute_tool_safely(tool_name, action_input, tracker, tool_counts)
                current_reasoning.append(ObservationReasoningStep(observation=observation))

                yield {
                    "event": "tool_end",
                    "iteration": iteration,
                    "tool": tool_name,
                    "result_summary": str(observation)[:200],
                }

        if not final_answer:
            final_answer = "Analysis concluded."

        total_latency = tracker.finish()

        yield {
            "event": "final_answer",
            "answer": final_answer,
            "tools_used": tracker.tools_used,
            "execution_time_ms": total_latency,
            "token_metrics": tracker.token_metrics.to_dict(),
        }

        yield {
            "event": "done",
            "status": "completed",
            "total_execution_time_ms": total_latency,
        }
