"""One chat call on the active AI (the one chosen in the sidebar or with `cosmolab ai`).

If the call fails or the AI sends back an empty or upstream-error answer, it is retried once
on the same AI. It never switches to another model behind the user's back: the answer always
comes from the AI the user picked, or the call fails with a clear error.
"""

import time

from openai import OpenAI
from rich.console import Console

from . import config

console = Console(force_terminal=True, legacy_windows=False)

# Text some gateways return in place of an answer when the model upstream fails.
_UPSTREAM_ERRORS = ("上游错误", "out of API credit")


def _answer(resp) -> str:
    choices = getattr(resp, "choices", None) or []
    message = getattr(choices[0], "message", None) if choices else None
    content = (getattr(message, "content", None) or "").strip() if message else ""
    return "" if any(e in content for e in _UPSTREAM_ERRORS) else content


def chat_text(system: str, user: str, model: str | None = None, temperature: float = 0.3,
              timeout: float = 120.0, label: str = "AI") -> str:
    """Return the active AI's answer to one system + user message, retrying once.

    Raises RuntimeError when both attempts fail or come back empty.
    """
    model = model or config.LLM_MODEL
    client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    problem = ""
    for attempt in (1, 2):
        try:
            resp = client.chat.completions.create(model=model, messages=messages, temperature=temperature,
                                                  timeout=timeout)
            content = _answer(resp)
            if content:
                return content
            problem = "jawaban AI kosong"
        except Exception as e:
            problem = str(e)[:200]
        if attempt == 1:
            console.print(f"[yellow]ULANG    [/yellow]{label}: {problem}. Coba sekali lagi dengan {model}.")
            time.sleep(2)
    raise RuntimeError(f"{model} gagal menjawab setelah 2 kali coba: {problem}")
