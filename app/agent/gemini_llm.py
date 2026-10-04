"""Modern Gemini LLM provider integration using the official Google GenAI SDK and CustomLLM."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, List, Optional, Sequence
from google import genai
from google.genai import types
from pydantic import PrivateAttr
from llama_index.core.llms.custom import CustomLLM
from llama_index.core.llms import LLM, LLMMetadata, CompletionResponse, ChatResponse
from llama_index.core.base.llms.types import ChatMessage, MessageRole

from app.agent.config import AgentConfig, get_agent_config
from app.services.dns_fallback import install_dns_fallback
from app.services.logging import get_logger

logger = get_logger("agentflow.llm")

# Ensure DNS fallback is always active before initializing LLM
install_dns_fallback()


class GeminiGenAI(CustomLLM):
    """Custom LlamaIndex LLM adapter using Google's modern GenAI SDK models.generate_content.

    Bypasses automatic function calling parser anomalies and Windows aiohttp DNS bugs by using
    pure text ReAct prompting with thread isolation.
    """

    model: str = "gemini-flash-lite-latest"
    api_key: str
    temperature: float = 0.1
    max_tokens: int = 2048
    _client: Any = PrivateAttr()

    def __init__(self, **data: Any):
        super().__init__(**data)
        self._client = genai.Client(api_key=self.api_key)

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            model_name=self.model,
            is_chat_model=True,
            context_window=32000,
            num_output=self.max_tokens,
        )

    def complete(self, prompt: str, **kwargs: Any) -> CompletionResponse:
        config = types.GenerateContentConfig(
            temperature=self.temperature,
            max_output_tokens=self.max_tokens,
        )
        resp = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        return CompletionResponse(text=resp.text or "")

    def stream_complete(self, prompt: str, **kwargs: Any):
        raise NotImplementedError("Streaming complete is not used in ReActAgent")

    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        # Build clean formatted contents for Gemini
        system_instructions: List[str] = []
        conversation_turns: List[str] = []

        for m in messages:
            if m.role == MessageRole.SYSTEM:
                system_instructions.append(m.content or "")
            elif m.role == MessageRole.USER:
                conversation_turns.append(f"User: {m.content or ''}")
            elif m.role == MessageRole.ASSISTANT:
                conversation_turns.append(f"Assistant: {m.content or ''}")
            else:
                conversation_turns.append(f"{m.role.value}: {m.content or ''}")

        full_prompt = ""
        if system_instructions:
            full_prompt += "\n".join(system_instructions) + "\n\n"
        full_prompt += "\n".join(conversation_turns)

        config = types.GenerateContentConfig(
            temperature=self.temperature,
            max_output_tokens=self.max_tokens,
        )

        for attempt in range(1, 4):
            try:
                resp = self._client.models.generate_content(
                    model=self.model,
                    contents=full_prompt,
                    config=config,
                )
                text = resp.text or ""
                return ChatResponse(message=ChatMessage(role=MessageRole.ASSISTANT, content=text))
            except Exception as exc:
                if attempt == 3:
                    logger.error(f"Gemini API call failed on attempt {attempt}: {exc}")
                    raise
                logger.warning(f"Transient Gemini API error (attempt {attempt}/3): {exc}. Retrying...")
                time.sleep(1.0)

        raise RuntimeError("Failed to generate content from Gemini API after retries.")

    async def achat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        """Asynchronous execution via worker thread to ensure non-blocking event loops."""
        return await asyncio.to_thread(self.chat, messages, **kwargs)


def create_gemini_llm(
    config: Optional[AgentConfig] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
) -> LLM:
    """Initializes the modern Google GenAI LLM for LlamaIndex ReActAgent."""
    cfg = config or get_agent_config()
    resolved_key = api_key or cfg.gemini_api_key or os.getenv("GEMINI_API_KEY")

    if not resolved_key or resolved_key.strip() in ("", "your_gemini_api_key_here"):
        raise ValueError(
            "GEMINI_API_KEY is not set or is empty. "
            "Please copy .env.example to .env and provide your Gemini API key from https://aistudio.google.com/app/apikey"
        )

    resolved_model = model or cfg.gemini_model or "gemini-flash-lite-latest"
    resolved_temp = temperature if temperature is not None else cfg.gemini_temperature

    logger.info(f"Initializing GeminiGenAI LLM with model='{resolved_model}', temperature={resolved_temp}")

    return GeminiGenAI(
        model=resolved_model,
        api_key=resolved_key,
        temperature=resolved_temp,
        max_tokens=cfg.max_output_tokens,
    )
