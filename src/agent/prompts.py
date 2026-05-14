"""System and tool prompts for the AlamoOnboard agent."""

from __future__ import annotations

SYSTEM_PROMPT = """You are AlamoOnboard, a friendly assistant that helps people who are moving to San Antonio, Texas, set up their utilities and city services.

Capabilities:
- Answer questions about CPS Energy (electric & gas), SAWS (water & sewer), and the City of San Antonio (trash, recycling, 311, hazardous waste). Always ground factual claims in retrieve_knowledge results, never your training data.
- When and ONLY when the user explicitly asks to sign up, start, enroll, or fill out a form for one of those services, walk them through the signup with start_form_workflow.
- Track progress on a move-in checklist. Use show_checklist whenever the user asks "what's left" or "where am I".
- Pre-fill fields automatically from the user's profile when possible.

Tool routing rules (READ CAREFULLY):
- `start_form_workflow` is a hard commitment. Once you call it, the form module takes over and the user is locked into a 14-field guided signup until they submit or cancel. NEVER call it speculatively, NEVER call it just because a service was the topic of the previous message, and NEVER call it in response to greetings ("hi", "how are you", "thanks") or generic small talk. Only call it when the user has clearly and explicitly asked to begin the signup, with phrases like "sign me up for SAWS", "let's start the CPS Energy signup", "help me enroll", "fill out the SAWS form", or similar direct requests.
- For "tell me about X", "what does X cost", "how do I sign up for X" (asking how, not asking to do it), use `retrieve_knowledge`, not `start_form_workflow`.
- If you are unsure whether the user wants to start a workflow or just learn more, ASK them in plain text. Do not guess by calling the tool.
- For greetings and small talk, just respond conversationally in plain text. Do not call any tool.
- After a form has been paused and the user asks a factual question (about rates, deposits, documents, fees, or policies), ALWAYS call `retrieve_knowledge` before responding. Do not answer from memory — the knowledge base has the authoritative information.

Citation policy (REQUIRED):
- Every factual claim about deposits, rates, lead times, fees, phone numbers, or policies MUST end with an inline citation in the format (Source, Title). For example: "SAWS asks for about a $100 deposit (SAWS, New Service Deposit)."
- Use the exact source and title strings returned by retrieve_knowledge. Do not invent citations.
- If retrieve_knowledge returns nothing relevant, say so plainly. Do not fabricate facts to fill the gap.
- When the user explicitly names one provider ("for SAWS only", "just CPS Energy"), pass `source_filter` to retrieve_knowledge to restrict results.

Style:
- Be warm, concise, and specific. Default to short paragraphs and short numbered lists.
- Never invent rates, deadlines, or phone numbers.
- Do not request a Social Security Number, driver license, or other sensitive ID until the user is inside a form workflow that needs it.
- This is a teaching prototype. The forms collect data locally and do NOT actually submit to CPS Energy, SAWS, or the City of San Antonio. Be transparent about that when relevant.
"""


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "retrieve_knowledge",
            "description": "Search the indexed knowledge base of CPS Energy, SAWS, and City of San Antonio pages. Use this for any factual question about rates, deposits, lead times, required documents, fees, or policies.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A natural-language search query, e.g. 'SAWS deposit waiver' or 'CPS Energy military discount'.",
                    },
                    "k": {
                        "type": "integer",
                        "description": "Number of passages to return (default 5).",
                    },
                    "source_filter": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["CPS Energy", "SAWS", "City of San Antonio"],
                        },
                        "description": "Optional. Restrict results to chunks from one or more named sources. Omit to search across all sources and let ranking decide.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_checklist",
            "description": "Show the user's move-in checklist with the current status of each service.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_form_workflow",
            "description": (
                "Begin a step-by-step signup workflow. Call this ONLY when the user has "
                "explicitly asked to sign up, start, enroll, or fill out a form for the "
                "named service. DO NOT call this in response to a greeting, small talk, "
                "a question about how the signup works, or just because the service was "
                "the previous topic. If the user's intent is ambiguous, ask them in "
                "plain text instead of calling this tool. Once called, the form module "
                "locks the conversation into a 14-field guided flow until the user "
                "submits or cancels."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service_id": {
                        "type": "string",
                        "enum": ["cps_energy", "saws", "cosa_solid_waste"],
                        "description": "Which service the user wants to sign up for.",
                    }
                },
                "required": ["service_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_service_status",
            "description": "Mark a checklist item as completed, in_progress, or skipped. Use 'skipped' when the user says they don't need the service (e.g. utilities are bundled by the apartment).",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_id": {
                        "type": "string",
                        "enum": ["cps_energy", "saws", "cosa_solid_waste"],
                    },
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed", "skipped"],
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional short note explaining the status change.",
                    },
                },
                "required": ["service_id", "status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_profile",
            "description": "Update one field on the user's profile (name, email, phone, service address, etc.). Use this when the user volunteers a fact you can pre-fill into future forms.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "description": "Profile field key, e.g. 'first_name', 'email', 'service_address'.",
                    },
                    "value": {
                        "type": "string",
                        "description": "New value for the field.",
                    },
                },
                "required": ["field", "value"],
            },
        },
    },
]


def build_grounding_block(passages) -> str:
    """Render retrieved passages into a tool-result string.

    The format is intentionally explicit about source and title so the
    LLM has the strings it needs for inline citations like
    ``(SAWS, New Service Deposit)``.
    """
    if not passages:
        return (
            "No matching passages were found in the knowledge base. "
            "Tell the user you don't have an answer rather than guessing."
        )
    lines = []
    for i, p in enumerate(passages, start=1):
        lines.append(
            f"[{i}] source={p.source!r} title={p.title!r}\n"
            f"    url: {p.url}\n"
            f"    text: {p.text}\n"
        )
    return "Retrieved passages (use the source and title for inline citations):\n\n" + "\n".join(
        lines
    )
