"""Unit tests for the AgentFlow ReAct Agent reasoning loop and tool orchestration."""

from pathlib import Path
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from llama_index.core.base.llms.types import ChatMessage, ChatResponse, MessageRole
from llama_index.core.llms.custom import CustomLLM
from llama_index.core.llms import LLMMetadata

from app.agent.agent import AgentFlowAgent, sanitize_final_answer
from app.agent.config import AgentConfig
from app.tools.tool_registry import get_agent_tools


class MockSequentialLLM(CustomLLM):
    """Deterministic Mock LLM returning sequential ReAct turns for testing."""

    responses: List[str]
    _current_index: int = 0

    def __init__(self, responses: List[str], **data: Any):
        super().__init__(responses=responses, **data)
        self._current_index = 0

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(model_name="mock-react-llm")

    async def achat(self, messages: List[ChatMessage], **kwargs: Any) -> ChatResponse:
        if self._current_index < len(self.responses):
            resp_text = self.responses[self._current_index]
            self._current_index += 1
        else:
            resp_text = "Thought: No more responses.\nAnswer: Final fallback answer."
        return ChatResponse(message=ChatMessage(role=MessageRole.ASSISTANT, content=resp_text))

    def complete(self, prompt: str, **kwargs: Any):
        raise NotImplementedError

    def stream_complete(self, prompt: str, **kwargs: Any):
        raise NotImplementedError


class TestAgentFlowEngine:
    """Verifies ReAct reasoning, multi-tool transitions, safety traces, and error resilience."""

    def test_sanitize_final_answer(self):
        raw = "Thought: I have computed the sum.\nAction: None\nAnswer: The total is 42."
        clean = sanitize_final_answer(raw)
        assert clean == "The total is 42."
        assert "Thought:" not in clean

    @pytest.mark.asyncio
    async def test_single_tool_execution(self, test_db: Path):
        mock_turns = [
            "Thought: I need to query customers.\nAction: sql_query\nAction Input: {\"query\": \"SELECT count(*) as count FROM customers\"}",
            "Thought: I have the count.\nAnswer: There are 12 registered customers in the database.",
        ]
        llm = MockSequentialLLM(responses=mock_turns)
        agent = AgentFlowAgent(llm=llm)

        result = await agent.achat("How many customers do we have?")
        assert result.success is True
        assert "12 registered customers" in result.answer
        assert result.tools_used == ["sql_query"]
        assert len(result.trace) == 1
        assert result.trace[0]["tool_name"] == "sql_query"
        assert result.trace[0]["status"] == "success"

    @pytest.mark.asyncio
    async def test_multi_tool_execution(self, test_db: Path):
        mock_turns = [
            "Thought: First I check web data.\nAction: web_search\nAction Input: {\"query\": \"Nvidia GPU trends\"}",
            "Thought: Next I query total sales.\nAction: sql_query\nAction Input: {\"query\": \"SELECT sum(total_amount) as total FROM orders\"}",
            "Thought: Now I calculate average.\nAction: execute_python\nAction Input: {\"code\": \"sales = 100; print(sales * 1.2)\"}",
            "Thought: I have all data.\nAnswer: The market is growing and our projected sales are 120.0.",
        ]
        llm = MockSequentialLLM(responses=mock_turns)
        agent = AgentFlowAgent(llm=llm)

        result = await agent.achat("Perform complete market and internal analysis.")
        assert result.success is True
        assert "projected sales are 120.0" in result.answer
        assert "web_search" in result.tools_used
        assert "sql_query" in result.tools_used
        assert "execute_python" in result.tools_used
        assert len(result.trace) == 3

    @pytest.mark.asyncio
    async def test_invalid_tool_argument_handled(self, test_db: Path):
        mock_turns = [
            'Thought: I will call SQL with malformed input.\nAction: sql_query\nAction Input: {"query": 99999}',
            "Thought: Recovered.\nAnswer: Query recovered and answered.",
        ]
        llm = MockSequentialLLM(responses=mock_turns)
        agent = AgentFlowAgent(llm=llm)

        result = await agent.achat("Query sales with bad arg")
        assert result.success is True
        assert "Query recovered and answered" in result.answer
        assert len(result.trace) == 1

    @pytest.mark.asyncio
    async def test_maximum_iterations_termination(self, test_db: Path):
        # Infinite loop simulation where model keeps repeating an action
        mock_turns = [
            "Thought: Looping.\nAction: execute_python\nAction Input: {\"code\": \"print(1)\"}",
            "Thought: Looping.\nAction: execute_python\nAction Input: {\"code\": \"print(2)\"}",
            "Thought: Looping.\nAction: execute_python\nAction Input: {\"code\": \"print(3)\"}",
        ]
        cfg = AgentConfig(max_agent_iterations=2)
        llm = MockSequentialLLM(responses=mock_turns)
        agent = AgentFlowAgent(llm=llm, config=cfg)

        result = await agent.achat("Run loop")
        # Ensure agent exits gracefully after 2 iterations
        assert result.answer is not None
        assert len(result.trace) <= 2

    @pytest.mark.asyncio
    async def test_tool_failure_recovery(self, test_db: Path):
        mock_turns = [
            # Attempt forbidden mutation
            "Thought: I will try to delete.\nAction: sql_query\nAction Input: {\"query\": \"DELETE FROM customers\"}",
            # Model observes validation rejection and explains to user
            "Thought: Deletion was blocked.\nAnswer: Cannot delete customers because only read-only SELECT queries are allowed.",
        ]
        llm = MockSequentialLLM(responses=mock_turns)
        agent = AgentFlowAgent(llm=llm)

        result = await agent.achat("Delete all customers")
        assert result.success is True
        assert "only read-only" in result.answer.lower()
        assert len(result.trace) == 1
        assert result.trace[0]["status"] == "success" or "error" in result.trace[0]["output_summary"]
