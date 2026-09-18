"""Patched history.py — drop-in replacement for agent_server/history.py.

Fixes the supervisor multi-turn bug where handoff tool_calls from prior turns
cause: "An assistant message with 'tool_calls' must be followed by tool messages
responding to each 'tool_call_id'".

Root cause: The supervisor uses handoffs, which internally create function_call
and function_call_output items. On the next user message, the chat UI replays
the full history including these items. The call_id values don't survive the
round-trip through the UI, so the model sees an assistant message with tool_calls
that has no matching tool response.

Fix: Strip function_call and function_call_output items from replayed history.
The SDK regenerates these for the current turn — only user messages and final
assistant text responses are needed for conversational context.

Usage:
    Copy this file into your app's agent_server/ directory as history.py,
    replacing the default template version:

        cp agents_on_apps/history_reference.py <your_app>/agent_server/history.py

    Then redeploy the app.
"""


def normalize_history_items(messages: list[dict]) -> list[dict]:
    """Normalize replayed assistant history items before passing them to Runner.run.

    Newer openai-agents converters only accept a typed assistant history item
    (``{"type": "message", "role": "assistant", ...}``) when it carries an
    ``id``, but clients replay the prior assistant turn without one: the
    built-in chat UI sends an id-less ``content`` list of ``output_text``
    parts, and MLflow evaluation sends plain-string ``content`` (MLflow's
    ``ResponsesAgentRequest`` has no ``id`` field, so any client-supplied id is
    stripped). Those items match no converter branch and raise
    ``UserError: Unhandled item type or structure`` on the second and later
    prompts.

    Collapse both shapes to the easy-input ``{"role", "content"}`` form, which
    every SDK version recognizes without an id. Multiple ``output_text``
    segments are joined with ``"\\n"`` to match the SDK converter's own
    behavior. Items that do carry an ``id`` alongside a content list are left
    untouched so the SDK's native handling (including ``refusal`` parts) still
    applies.
    """
    normalized: list[dict] = []
    for m in messages:
        # ---- PATCH: strip orphaned handoff tool_calls from prior turns ----
        # The supervisor's handoff function_call / function_call_output items
        # don't survive the round-trip through the chat UI — call IDs are
        # lost, so the model sees an assistant message with tool_calls that
        # has no matching tool response. The SDK regenerates these as needed
        # for the current turn; only user/assistant text is needed for context.
        if m.get("type") in ("function_call", "function_call_output"):
            continue
        # ---- END PATCH ----

        if m.get("type") != "message" or m.get("role") != "assistant":
            normalized.append(m)
            continue
        content = m.get("content")
        if isinstance(content, str):
            normalized.append({"role": "assistant", "content": content})
        elif isinstance(content, list) and "id" not in m:
            text = "\n".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "output_text"
            )
            normalized.append({"role": "assistant", "content": text})
        else:
            normalized.append(m)
    return normalized
