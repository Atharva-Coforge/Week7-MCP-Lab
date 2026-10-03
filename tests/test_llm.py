import pytest

from equipment_agent.llm import (
    LLMConnectionError,
    OllamaAdapter,
    mcp_tools_to_ollama,
    reply_from_message,
)


class _Function:
    def __init__(self, name: str, arguments: object) -> None:
        self.name = name
        self.arguments = arguments


class _Call:
    def __init__(self, name: str, arguments: object) -> None:
        self.function = _Function(name, arguments)


class _Message:
    def __init__(self, content: str, calls: list[_Call]) -> None:
        self.content = content
        self.tool_calls = calls


class _Response:
    def __init__(self, message: _Message) -> None:
        self.message = message


class _Tool:
    name = "get_employee_info"
    description = "Look up an employee."

    def model_dump(self, by_alias: bool = True) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {"type": "object", "properties": {}},
        }


class _Client:
    def __init__(self, response: _Response | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.kwargs: dict | None = None

    async def chat(self, **kwargs: object) -> _Response:
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


@pytest.mark.anyio
async def test_ollama_adapter_calls_the_model_and_returns_tool_calls():
    client = _Client(
        _Response(_Message("Thought: Look up the employee.", [_Call("get_employee_info", '{"employee_id": "E101"}')]))
    )
    adapter = OllamaAdapter(model="qwen3:8b", host="http://host.docker.internal:11434", client=client)

    reply = await adapter.chat([{"role": "user", "content": "E101"}], [_Tool()])

    assert client.kwargs is not None
    assert client.kwargs["model"] == "qwen3:8b"
    assert client.kwargs["tools"] == mcp_tools_to_ollama([_Tool()])
    assert reply.tool_calls == [("get_employee_info", {"employee_id": "E101"})]
    assert reply.assistant_message["role"] == "assistant"
    assert reply.assistant_message["tool_calls"][0]["function"]["name"] == "get_employee_info"


@pytest.mark.anyio
async def test_ollama_adapter_reports_a_dead_server():
    adapter = OllamaAdapter(
        model="qwen3:8b",
        host="http://host.docker.internal:11434",
        client=_Client(error=ConnectionError("refused")),
    )

    with pytest.raises(LLMConnectionError, match="host.docker.internal:11434"):
        await adapter.chat([], [])


def test_reply_without_tool_calls_keeps_the_text():
    reply = reply_from_message(_Message("Decision: approved\nWithin policy.", []))

    assert reply.content.startswith("Decision: approved")
    assert reply.tool_calls == []
    assert "tool_calls" not in reply.assistant_message
