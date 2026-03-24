"""
Centralised LLM factory.

All modules call get_llm(task) instead of building their own client.
Switching provider or model requires a change in only one place.

Task tiers
----------
"fast"  — structured JSON tasks: input understanding, diagnosis scoring,
           evaluation scoring, generating eval questions.
           Prioritises speed and cost. Smaller model is fine.

"rich"  — long-form generation: lesson planning, section delivery,
           interruption answers.
           Prioritises quality and coherence. Larger model preferred.

Groq models used
----------------
fast : llama-3.1-8b-instant   (very fast, ~500 tok/s, great for JSON)
rich : llama-3.3-70b-versatile (best open model on Groq for long generation)

Cerebras models used  (free tier: 30 RPM, ~2000 tok/s — fastest free option)
--------------------
fast : llama3.1-8b
rich : qwen-3-235b-a22b-instruct-2507

Google Gemini models used  (free tier: 1,500 RPD / 1,000,000 TPM — region-dependent)
-------------------------
fast : gemini-2.0-flash
rich : gemini-2.5-flash
"""
from app.core.config import settings


def get_llm(task: str = "fast"):
    """
    Return the appropriate LangChain chat model for the given task tier.

    Parameters
    ----------
    task : "fast" | "rich"
    """
    provider = settings.default_llm_provider

    if provider == "groq":
        from langchain_groq import ChatGroq
        model = (
            "llama-3.1-8b-instant"      if task == "fast"
            else "llama-3.3-70b-versatile"
        )
        return ChatGroq(model=model, api_key=settings.groq_api_key)

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        model = (
            "claude-haiku-4-5-20251001" if task == "fast"
            else "claude-sonnet-4-6"
        )
        return ChatAnthropic(model=model, api_key=settings.anthropic_api_key)

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        model = (
            "gpt-4o-mini" if task == "fast"
            else "gpt-4o"
        )
        return ChatOpenAI(model=model, api_key=settings.openai_api_key)

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        model = (
            "gemini-2.0-flash" if task == "fast"
            else "gemini-2.5-flash"
        )
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.gemini_api_key,
        )

    if provider == "cerebras":
        from langchain_openai import ChatOpenAI
        model = (
            "llama3.1-8b" if task == "fast"
            else "qwen-3-235b-a22b-instruct-2507"
        )
        return ChatOpenAI(
            model=model,
            api_key=settings.cerebras_api_key,
            base_url="https://api.cerebras.ai/v1",
        )

    raise ValueError(
        f"Unknown LLM provider '{provider}'. "
        "Set DEFAULT_LLM_PROVIDER to 'groq', 'anthropic', 'openai', 'gemini', or 'cerebras'."
    )
