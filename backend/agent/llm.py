"""Model registry — one model per job.

Groq meters rate limits per model, not per key, so putting each kind of work on
its own model multiplies the free tier's effective throughput. A 4,000-token
assignment no longer eats the budget Ash needs to answer a chat message.

Roles:
  conversation — chat and tool calls. Stays on qwen: in testing it emitted the
                 text-JSON tool convention 8 times out of 9, where
                 gpt-oss-120b managed 2 of 9.
  extraction   — memory summarizing. JSON in, JSON out, no tools; the small
                 model is as accurate here and keeps the conversation model's
                 budget free.
  longform     — assignments and itineraries. Big outputs (up to 4,000 tokens)
                 on their own bucket, so a long write can't starve chat.

Override any role from .env with ASH_MODEL_CONVERSATION / _EXTRACTION /
_LONGFORM to try a different model without touching code.
"""

import os

from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"), max_retries=4)

MODELS = {
    "conversation": os.getenv("ASH_MODEL_CONVERSATION", "qwen/qwen3.8-27b"),
    "extraction": os.getenv("ASH_MODEL_EXTRACTION", "openai/gpt-oss-20b"),
    "longform": os.getenv("ASH_MODEL_LONGFORM", "openai/gpt-oss-120b"),
}

# qwen leaks <think> blocks into documents unless reasoning is off; the gpt-oss
# models return reasoning in a separate field, so a low effort is safe there.
_EXTRA_BODY = {
    "qwen/qwen3.8-27b": {"reasoning_effort": "none"},
    "qwen/qwen3.6-27b": {"reasoning_effort": "none"},
    "openai/gpt-oss-20b": {"reasoning_effort": "low"},
    "openai/gpt-oss-120b": {"reasoning_effort": "low"},
}


def model_for(role: str) -> str:
    """The model id configured for *role*."""
    return MODELS[role]


def complete(role: str, messages: list, max_tokens: int = None, **kwargs):
    """Run a completion for *role* and return the raw Groq response."""
    model = MODELS[role]
    extra = dict(_EXTRA_BODY.get(model, {}))
    extra.update(kwargs.pop("extra_body", None) or {})
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return client.chat.completions.create(
        model=model,
        messages=messages,
        extra_body=extra,
        **kwargs,
    )
