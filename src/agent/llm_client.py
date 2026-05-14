"""LLM client wrapper.

Supports any OpenAI-compatible chat-completions endpoint. The
``ALAMO_LLM_BASE_URL`` env var lets the same code talk to OpenAI, a
locally running vLLM, or a proxied endpoint such as the UTSA internal
API. When no API key is available the module falls back to a tiny
rule-based stub so the rest of the system can still be demoed.
"""

from __future__ import annotations

import json
import re
from typing import Any

from config import DEMO_MODE, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


# Inline tool-call extraction
#
# Some OpenAI-compatible servers emit tool calls as JSON inside the assistant's
# content field rather than via the structured tool_calls field. Two common shapes
# are tolerated:
#   {"type": "function", "name": "X", "parameters": {...}}
#   {"name": "X", "arguments": {...}}
#
# _iter_json_objects uses brace-matching (not regex) because values can contain
# nested braces. Multiple calls per message are supported.

_TOOL_CALL_HINTS = ('"name"', '"function"', '"parameters"', '"arguments"')


def _iter_json_objects(text: str):
    """Yield ``(start, end, parsed_dict)`` for each balanced JSON object.

    Skips bytes that are not part of a JSON object. Tolerates surrounding
    prose, code fences, and multiple objects.
    """
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        in_str = False
        esc = False
        for j in range(i, n):
            c = text[j]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    snippet = text[i : j + 1]
                    try:
                        obj = json.loads(snippet)
                    except json.JSONDecodeError:
                        obj = None
                    if isinstance(obj, dict):
                        yield i, j + 1, obj
                    i = j + 1
                    break
        else:
            # Unbalanced braces; bail out.
            return


def _extract_inline_tool_calls(content: str) -> list[dict]:
    """Find tool-call JSON objects inside an assistant message.

    Returns a list of structured tool-call dicts in the same shape we use
    for native ``tool_calls`` (``{id, name, arguments}``). Empty if
    nothing parseable was found.
    """
    if not any(hint in content for hint in _TOOL_CALL_HINTS):
        return []

    calls: list[dict] = []
    for idx, (_start, _end, obj) in enumerate(_iter_json_objects(content)):
        name = obj.get("name") or (obj.get("function") or {}).get("name")
        if not name or not isinstance(name, str):
            continue
        # Argument shape can be either "parameters" or "arguments".
        args = obj.get("parameters")
        if args is None:
            args = obj.get("arguments")
        if args is None and isinstance(obj.get("function"), dict):
            args = obj["function"].get("arguments")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            # Some servers double-encode the arguments as a JSON string.
            try:
                args = json.loads(args) if isinstance(args, str) else {}
            except json.JSONDecodeError:
                args = {}
        calls.append({"id": f"inline-{idx}", "name": name, "arguments": args})

    if calls:
        logger.info("extracted %d inline tool call(s) from assistant content", len(calls))
    return calls


# Match ```json ... ``` and ``` ... ``` fences around tool-call objects.
_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _strip_inline_tool_calls(content: str) -> str:
    """Remove tool-call JSON (and any code fences around it) from the text.

    Used after we've successfully parsed inline tool calls so the user
    doesn't see the raw JSON in the chat.
    """

    # First strip fenced code blocks containing tool-call JSON.
    def _maybe_drop(match: re.Match) -> str:
        body = match.group(1)
        if any(hint in body for hint in _TOOL_CALL_HINTS):
            return ""
        return match.group(0)

    cleaned = _FENCE_RE.sub(_maybe_drop, content)

    # Then strip bare tool-call JSON objects (no fences).
    drop_spans: list[tuple[int, int]] = []
    for start, end, obj in _iter_json_objects(cleaned):
        name = obj.get("name") or (obj.get("function") or {}).get("name")
        if (
            name
            and isinstance(name, str)
            and ("parameters" in obj or "arguments" in obj or "function" in obj)
        ):
            drop_spans.append((start, end))
    for start, end in reversed(drop_spans):
        cleaned = cleaned[:start] + cleaned[end:]
    return cleaned.strip()


class LLMClient:
    """Minimal chat-completions client with optional tool-calling."""

    def __init__(
        self,
        model: str = LLM_MODEL,
        base_url: str | None = LLM_BASE_URL,
        api_key: str | None = LLM_API_KEY,
        demo_mode: bool = DEMO_MODE,
    ):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.demo_mode = demo_mode
        self._client = None
        if not demo_mode:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=api_key, base_url=base_url)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("OpenAI client unavailable, dropping to demo mode: %s", exc)
                self.demo_mode = True

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
    ) -> dict:
        """Send a chat-completion request.

        Returns a normalized dict of the form::

            {"content": str, "tool_calls": list[dict]}

        ``tool_calls`` is empty when the model did not request a tool.
        """
        if self.demo_mode or self._client is None:
            return self._demo_chat(messages, tools)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self._client.chat.completions.create(**kwargs)
        choice = response.choices[0].message
        out: dict[str, Any] = {"content": choice.content or "", "tool_calls": []}
        if getattr(choice, "tool_calls", None):
            for tc in choice.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                out["tool_calls"].append({"id": tc.id, "name": tc.function.name, "arguments": args})

        # Fallback: some OpenAI-compatible servers return tool calls as JSON inside the
        # content field rather than the structured tool_calls field. _extract_inline_tool_calls
        # detects this and synthesizes structured calls so the orchestrator can act on them.
        if not out["tool_calls"] and out["content"]:
            extracted = _extract_inline_tool_calls(out["content"])
            if extracted:
                out["tool_calls"] = extracted
                # Strip the JSON from the visible content so the user
                # doesn't see the raw call. If parsing consumed the
                # whole message, leave content empty.
                out["content"] = _strip_inline_tool_calls(out["content"])
        return out

    def _demo_chat(self, messages: list[dict], tools: list[dict] | None) -> dict:
        """Cheap stand-in when no API key is present.

        First turn: request the ``retrieve_knowledge`` tool with the
        user's latest message as the query. Second turn (after a tool
        result lands in the message list): summarize the snippets in
        plain prose so the orchestrator loop terminates instead of
        re-issuing the same tool call.
        """
        # Find the most recent tool message (the retrieval result, if any)
        latest_tool_msg = next(
            (m for m in reversed(messages) if m.get("role") == "tool"),
            None,
        )

        # Find the latest user message (skip assistant/tool/system)
        latest_user_msg = next(
            (m for m in reversed(messages) if m.get("role") == "user"),
            None,
        )
        user_text = (latest_user_msg.get("content") if latest_user_msg else "") or ""
        user_text = user_text.strip()

        # If retrieval already happened, synthesize an answer from it.
        if latest_tool_msg is not None:
            snippets = (latest_tool_msg.get("content") or "").strip()
            preface = "_(demo mode - rule-based summary of retrieval results)_\n\n"
            if not snippets:
                return {
                    "content": (
                        preface + "I searched the knowledge base but did not find a confident "
                        "match. Try rephrasing or set `ALAMO_LLM_API_KEY` for a real LLM."
                    ),
                    "tool_calls": [],
                }
            return {
                "content": (
                    preface + f'Here is what I found about "{user_text}":\n\n{snippets}\n\n'
                    "Set `ALAMO_LLM_API_KEY` (and optionally `ALAMO_LLM_BASE_URL`) for a "
                    "more conversational reply."
                ),
                "tool_calls": [],
            }

        # No retrieval has happened yet - request one if the tool is offered.
        if tools and any(t["function"]["name"] == "retrieve_knowledge" for t in tools):
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "demo-tool-1",
                        "name": "retrieve_knowledge",
                        "arguments": {"query": user_text or "moving to San Antonio"},
                    }
                ],
            }
        return {
            "content": (
                "_(running in demo mode without an LLM)_\n\n"
                "I can still search the knowledge base, walk you through forms, and update "
                "your checklist. Set `ALAMO_LLM_API_KEY` (and optionally `ALAMO_LLM_BASE_URL`) "
                "to enable full conversational answers."
            ),
            "tool_calls": [],
        }
