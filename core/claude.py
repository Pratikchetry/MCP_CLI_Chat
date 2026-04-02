"""
Groq-backed Claude adapter.

Exposes the same interface as the original Anthropic-based Claude class so
the rest of the codebase needs no changes.  Internally it:
  1. Converts Anthropic-format messages  → OpenAI/Groq format
  2. Converts Anthropic-format tools     → OpenAI/Groq format
  3. Calls the Groq API
  4. Converts the Groq response          → Anthropic-like Message objects
"""

import json
from groq import Groq


# ---------------------------------------------------------------------------
# Lightweight stand-ins for the Anthropic SDK types used elsewhere
# ---------------------------------------------------------------------------

class TextBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class ToolUseBlock:
    def __init__(self, id: str, name: str, input: dict):
        self.type = "tool_use"
        self.id = id
        self.name = name
        self.input = input


class Message:
    """Mimics anthropic.types.Message well enough for the rest of the app."""
    def __init__(self, content: list, stop_reason: str):
        self.content = content
        self.stop_reason = stop_reason


# ---------------------------------------------------------------------------
# Helper: safely read an attribute that may be a dict key or object attr
# ---------------------------------------------------------------------------

def _get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class Claude:
    def __init__(self, model: str):
        self.client = Groq()   # reads GROQ_API_KEY from env automatically
        self.model = model

    # ------------------------------------------------------------------
    # Message-list helpers (same API as the original class)
    # ------------------------------------------------------------------

    def add_user_message(self, messages: list, message):
        content = message.content if hasattr(message, "content") else message
        messages.append({"role": "user", "content": content})

    def add_assistant_message(self, messages: list, message):
        content = message.content if hasattr(message, "content") else message
        messages.append({"role": "assistant", "content": content})

    def text_from_message(self, message: "Message") -> str:
        return "\n".join(
            block.text for block in message.content if block.type == "text"
        )

    # ------------------------------------------------------------------
    # Format converters
    # ------------------------------------------------------------------

    def _convert_messages(self, messages: list) -> list:
        """Anthropic message list → OpenAI/Groq message list."""
        result = []
        for msg in messages:
            role    = msg["role"]
            content = msg["content"]

            if isinstance(content, str):
                result.append({"role": role, "content": content})

            elif isinstance(content, list):
                if not content:
                    result.append({"role": role, "content": ""})
                    continue

                first_type = _get(content[0], "type")

                # tool-result blocks → separate Groq "tool" messages
                if role == "user" and first_type == "tool_result":
                    for item in content:
                        result.append({
                            "role":         "tool",
                            "tool_call_id": _get(item, "tool_use_id", ""),
                            "content":      _get(item, "content", "") or "",
                        })

                # assistant content blocks (text + tool_use)
                elif role == "assistant":
                    text_parts = []
                    tool_calls = []
                    for block in content:
                        btype = _get(block, "type")
                        if btype == "text":
                            t = _get(block, "text", "")
                            if t:
                                text_parts.append(t)
                        elif btype == "tool_use":
                            tool_calls.append({
                                "id":   _get(block, "id", ""),
                                "type": "function",
                                "function": {
                                    "name":      _get(block, "name", ""),
                                    "arguments": json.dumps(_get(block, "input", {})),
                                },
                            })
                    openai_msg = {
                        "role":    "assistant",
                        "content": " ".join(text_parts) if text_parts else None,
                    }
                    if tool_calls:
                        openai_msg["tool_calls"] = tool_calls
                    result.append(openai_msg)

                # user message with text blocks (from prompt templates)
                else:
                    texts = [
                        _get(item, "text", "")
                        for item in content
                        if _get(item, "type") == "text"
                    ]
                    result.append({"role": role, "content": " ".join(texts)})

            else:
                result.append({"role": role, "content": str(content)})

        return result

    def _convert_tools(self, tools: list) -> list:
        """Anthropic tool dicts → OpenAI/Groq tool dicts."""
        return [
            {
                "type": "function",
                "function": {
                    "name":        t["name"],
                    "description": t.get("description", ""),
                    "parameters":  t.get(
                        "input_schema",
                        {"type": "object", "properties": {}},
                    ),
                },
            }
            for t in tools
        ]

    def _convert_response(self, groq_response) -> Message:
        """Groq completion → our Message."""
        choice      = groq_response.choices[0]
        msg         = choice.message

        content     = []
        stop_reason = "end_turn"

        if msg.content:
            content.append(TextBlock(msg.content))

        if msg.tool_calls:
            stop_reason = "tool_use"
            for tc in msg.tool_calls:
                content.append(ToolUseBlock(
                    id    = tc.id,
                    name  = tc.function.name,
                    input = json.loads(tc.function.arguments),
                ))

        return Message(content=content, stop_reason=stop_reason)

    # ------------------------------------------------------------------
    # Main chat method (same signature as original)
    # ------------------------------------------------------------------

    def chat(
        self,
        messages,
        system           = None,
        temperature      = 1.0,
        stop_sequences   = [],
        tools            = None,
        thinking         = False,
        thinking_budget  = 1024,
    ) -> Message:

        openai_messages = []
        if system:
            openai_messages.append({"role": "system", "content": system})
        openai_messages += self._convert_messages(messages)

        params = {
            "model":       self.model,
            "max_tokens":  4096,
            "messages":    openai_messages,
            "temperature": min(float(temperature), 2.0),
        }

        if stop_sequences:
            params["stop"] = stop_sequences

        if tools:
            params["tools"]       = self._convert_tools(tools)
            params["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**params)
        return self._convert_response(response)
