from coding_agent.llm.base import LLMProvider, LLMResponse
from coding_agent.llm.openai_provider import OpenAIProvider

__all__ = ["LLMProvider", "LLMResponse", "OpenAIProvider"]


def create_provider(config) -> LLMProvider:
    if config.llm_provider == "openai":
        return OpenAIProvider(
            api_key=config.llm_api_key,
            model=config.llm_model,
            base_url=config.llm_base_url,
        )
    if config.llm_provider == "anthropic":
        from coding_agent.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            api_key=config.llm_api_key,
            model=config.llm_model,
            base_url=config.llm_base_url,
        )
    msg = f"Unsupported LLM provider: {config.llm_provider}"
    raise ValueError(msg)
