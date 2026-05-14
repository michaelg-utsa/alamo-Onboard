"""Unit tests for src/agent/llm_client.py — demo mode and inline-tool helpers."""

from __future__ import annotations

import os

os.environ.setdefault("ALAMO_DEMO_MODE", "1")
os.environ.setdefault("ALAMO_LLM_API_KEY", "")


class TestIterJsonObjects:
    def test_finds_single_object(self):
        from src.agent.llm_client import _iter_json_objects

        text = 'before {"name": "foo"} after'
        results = list(_iter_json_objects(text))
        assert len(results) == 1
        _, _, obj = results[0]
        assert obj["name"] == "foo"

    def test_finds_multiple_objects(self):
        from src.agent.llm_client import _iter_json_objects

        text = '{"a": 1} some text {"b": 2}'
        results = list(_iter_json_objects(text))
        assert len(results) == 2

    def test_skips_invalid_json(self):
        from src.agent.llm_client import _iter_json_objects

        text = '{"valid": true} {not valid}'
        results = list(_iter_json_objects(text))
        assert len(results) == 1

    def test_empty_string(self):
        from src.agent.llm_client import _iter_json_objects

        results = list(_iter_json_objects(""))
        assert results == []

    def test_no_braces(self):
        from src.agent.llm_client import _iter_json_objects

        results = list(_iter_json_objects("no braces here"))
        assert results == []

    def test_nested_objects(self):
        from src.agent.llm_client import _iter_json_objects

        text = '{"outer": {"inner": 1}}'
        results = list(_iter_json_objects(text))
        assert len(results) == 1
        _, _, obj = results[0]
        assert obj["outer"]["inner"] == 1


class TestExtractInlineToolCalls:
    def test_extracts_name_and_parameters(self):
        from src.agent.llm_client import _extract_inline_tool_calls

        content = '{"name": "retrieve_knowledge", "parameters": {"query": "CPS deposit"}}'
        calls = _extract_inline_tool_calls(content)
        assert len(calls) == 1
        assert calls[0]["name"] == "retrieve_knowledge"
        assert calls[0]["arguments"]["query"] == "CPS deposit"

    def test_extracts_function_wrapper(self):
        from src.agent.llm_client import _extract_inline_tool_calls

        content = '{"function": {"name": "retrieve_knowledge"}, "arguments": {"query": "SAWS"}}'
        calls = _extract_inline_tool_calls(content)
        assert len(calls) == 1
        assert calls[0]["name"] == "retrieve_knowledge"

    def test_no_hints_returns_empty(self):
        from src.agent.llm_client import _extract_inline_tool_calls

        content = "Just a normal response without tool calls."
        calls = _extract_inline_tool_calls(content)
        assert calls == []

    def test_empty_content_returns_empty(self):
        from src.agent.llm_client import _extract_inline_tool_calls

        calls = _extract_inline_tool_calls("")
        assert calls == []

    def test_multiple_calls(self):
        from src.agent.llm_client import _extract_inline_tool_calls

        content = (
            '{"name": "retrieve_knowledge", "parameters": {"query": "CPS"}} '
            "some text "
            '{"name": "mark_status", "parameters": {"service": "cps_energy", "status": "completed"}}'
        )
        calls = _extract_inline_tool_calls(content)
        assert len(calls) == 2


class TestStripInlineToolCalls:
    def test_strips_json_object(self):
        from src.agent.llm_client import _strip_inline_tool_calls

        content = (
            'Here is my answer. {"name": "retrieve_knowledge", "parameters": {"query": "test"}}'
        )
        result = _strip_inline_tool_calls(content)
        assert "retrieve_knowledge" not in result
        assert "Here is my answer" in result

    def test_strips_fenced_code_block(self):
        from src.agent.llm_client import _strip_inline_tool_calls

        content = 'Text before\n```json\n{"name": "retrieve_knowledge", "parameters": {}}\n```\nText after'
        result = _strip_inline_tool_calls(content)
        assert "retrieve_knowledge" not in result

    def test_preserves_non_tool_content(self):
        from src.agent.llm_client import _strip_inline_tool_calls

        content = "This is a normal response."
        result = _strip_inline_tool_calls(content)
        assert result == content


class TestLLMClientDemoMode:
    def _make_client(self):
        from src.agent.llm_client import LLMClient

        return LLMClient(demo_mode=True)

    def test_demo_mode_flag(self):
        client = self._make_client()
        assert client.demo_mode is True

    def test_chat_without_tools_returns_content(self):
        client = self._make_client()
        result = client.chat([{"role": "user", "content": "Hello"}])
        assert "content" in result
        assert "tool_calls" in result
        assert result["content"]
        assert result["tool_calls"] == []

    def test_chat_with_retrieve_tool_requests_it(self):
        client = self._make_client()
        tools = [{"function": {"name": "retrieve_knowledge"}}]
        result = client.chat(
            [{"role": "user", "content": "What is the CPS deposit?"}],
            tools=tools,
        )
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "retrieve_knowledge"

    def test_chat_with_tool_result_returns_answer(self):
        client = self._make_client()
        messages = [
            {"role": "user", "content": "What is the CPS deposit?"},
            {"role": "assistant", "content": ""},
            {"role": "tool", "content": "CPS requires $200 deposit for new accounts."},
        ]
        result = client.chat(messages)
        assert result["tool_calls"] == []
        assert result["content"]

    def test_chat_with_empty_tool_result_returns_fallback(self):
        client = self._make_client()
        messages = [
            {"role": "user", "content": "weird query"},
            {"role": "tool", "content": ""},
        ]
        result = client.chat(messages)
        assert result["content"]
        assert result["tool_calls"] == []

    def test_demo_chat_uses_user_text_as_query(self):
        client = self._make_client()
        tools = [{"function": {"name": "retrieve_knowledge"}}]
        result = client.chat(
            [{"role": "user", "content": "SAWS deposit amount"}],
            tools=tools,
        )
        assert result["tool_calls"][0]["arguments"]["query"] == "SAWS deposit amount"
