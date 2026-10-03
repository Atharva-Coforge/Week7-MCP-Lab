"""Model adapter. The ReAct loop talks to this, not to a vendor client.

`OllamaAdapter` is the implementation that calls Ollama. A different model is
another class with the same `chat` method.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from ollama import AsyncClient, ResponseError

# This process runs in a container. Ollama listens on the host, not on the container's localhost.
DEFAULT_OLLAMA_HOST = "http://host.docker.internal:11434"
DEFAULT_OLLAMA_MODEL = "qwen3:8b"


class LLMError(Exception):
    """A model call failed."""


class LLMConnectionError(LLMError):
    """The model server could not be reached."""

    def __init__(self, host: str) -> None:
        super().__init__(f"Ollama is not reachable at {host}. Start it with `ollama serve`.")


@dataclass(frozen=True)
class ChatReply:
    """One assistant turn, independent of the model vendor."""

    content: str
    tool_calls: list[tuple[str, dict]]
    assistant_message: dict[str, Any]


class LLMAdapter(Protocol):
    """What the ReAct loop needs from any model."""

    async def chat(self, messages: list[dict[str, Any]], tools: list[Any]) -> ChatReply:
        """Return the next assistant turn for this transcript and these tools."""


class OllamaAdapter:
    """Call a local Ollama model and return a vendor-neutral reply."""

    def __init__(self, model: str, host: str, client: Any | None = None) -> None:
        self.model = model
        self.host = host
        self._client = client if client is not None else AsyncClient(host=host)

    async def chat(self, messages: list[dict[str, Any]], tools: list[Any]) -> ChatReply:
        try:
            response = await self._client.chat(
                model=self.model,
                messages=messages,
                tools=mcp_tools_to_ollama(tools),
                think=False,
                stream=False,
                options={"temperature": 0},
            )
        except (httpx.ConnectError, ConnectionError) as exc:
            raise LLMConnectionError(self.host) from exc
        except ResponseError as exc:
            raise LLMError(f"Ollama request failed: {exc}") from exc
        return reply_from_message(response.message)


def ollama_adapter(model: str | None = None, host: str | None = None) -> OllamaAdapter:
    """The adapter the agent uses unless a caller passes a different one."""
    return OllamaAdapter(
        model=model or os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
        host=host or ollama_host(),
    )


def ollama_host() -> str:
    """Ollama base URL. `OLLAMA_HOST` overrides the container default."""
    return os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)


def mcp_tools_to_ollama(tools: list[Any]) -> list[dict]:
    """Turn MCP tool definitions into the tool list Ollama's chat API expects."""
    converted = []
    for tool in tools:
        if isinstance(tool, dict) and "function" in tool:
            converted.append(tool)
            continue
        data = tool.model_dump(by_alias=True) if hasattr(tool, "model_dump") else dict(tool)
        schema = data.get("inputSchema") or data.get("input_schema") or {"type": "object", "properties": {}}
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": data.get("name") or tool.name,
                    "description": data.get("description") or "",
                    "parameters": schema,
                },
            }
        )
    return converted


def reply_from_message(message: object) -> ChatReply:
    """Copy an Ollama message into a reply the loop can store as a plain dict."""
    content = getattr(message, "content", None) or ""
    calls: list[tuple[str, dict]] = []
    for call in getattr(message, "tool_calls", None) or []:
        function = call.function
        calls.append((function.name, _coerce_args(function.arguments)))
    assistant: dict[str, Any] = {"role": "assistant", "content": content}
    if calls:
        assistant["tool_calls"] = [{"function": {"name": name, "arguments": args}} for name, args in calls]
    return ChatReply(content=content, tool_calls=calls, assistant_message=assistant)


def _coerce_args(raw: object) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return {}
    return dict(raw) if isinstance(raw, dict) else {}
