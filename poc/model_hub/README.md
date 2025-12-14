# Model Hub POC - Multi-Provider LLM Integration

A proof of concept implementation for integrating multiple Large Language Model providers with a unified interface.

## Overview

The Model Hub provides a unified interface for interacting with multiple LLM providers, allowing easy switching between different models and providers without changing application code.

## Features

- **Provider Abstraction**: Unified interface for different LLM providers
- **Dynamic Provider Loading**: Add new providers without code changes
- **Configuration Management**: Environment-based provider configuration
- **Error Handling**: Consistent error handling across providers
- **Async Support**: Full async/await support for all operations
- **Type Safety**: Full type hints and Pydantic validation

## Supported Providers

- **OpenAI** (GPT-3.5, GPT-4, etc.)
- **Anthropic** (Claude models)
- **Google** (Gemini models)
- **Groq** (Mixtral, LLaMA, etc.)
- **Local Models** (via Hugging Face Transformers)
- **Custom Providers** (extensible interface)

## Quick Start

```python
from model_hub import ModelHub

# Initialize the hub
hub = ModelHub()

# Configure providers (via environment variables or config)
# OPENAI_API_KEY=your_key
# ANTHROPIC_API_KEY=your_key

# Use a specific provider and model
response = await hub.generate(
    provider="openai",
    model="gpt-4",
    prompt="Hello, how are you?",
    max_tokens=100
)

print(response.text)
```

## Architecture

```
model_hub/
├── hub.py              # Main ModelHub class
├── providers/          # Provider implementations
│   ├── base.py         # Base provider interface
│   ├── openai.py       # OpenAI provider
│   ├── anthropic.py    # Anthropic provider
│   ├── google.py       # Google provider
│   ├── groq.py         # Groq provider
│   └── local.py        # Local/HuggingFace provider
├── config.py           # Configuration management
├── exceptions.py       # Custom exceptions
└── model_types.py      # Type definitions
```

## Configuration

Configure providers using environment variables:

```bash
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_DEFAULT_MODEL=gpt-4

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_DEFAULT_MODEL=claude-3-sonnet-20240229

# Google
GOOGLE_API_KEY=...
GOOGLE_DEFAULT_MODEL=gemini-pro

# Groq
GROQ_API_KEY=gsk-...
GROQ_DEFAULT_MODEL=mixtral-8x7b-32768

# Local Models
LOCAL_DEFAULT_MODEL=microsoft/DialoGPT-medium
```

## Usage Examples

### Basic Text Generation

```python
from model_hub import ModelHub

hub = ModelHub()

# Generate text
response = await hub.generate(
    provider="openai",
    model="gpt-4",
    prompt="Explain quantum computing in simple terms",
    temperature=0.7,
    max_tokens=500
)

print(response.text)
print(f"Tokens used: {response.usage.total_tokens}")
```

### Streaming Responses

```python
# Stream responses for real-time output
async for chunk in hub.stream_generate(
    provider="anthropic",
    model="claude-3-sonnet-20240229",
    prompt="Write a short story about AI",
    max_tokens=1000
):
    print(chunk.text, end="", flush=True)
```

### Provider Switching

```python
# Same code, different providers
providers = ["openai", "anthropic", "google"]

for provider in providers:
    response = await hub.generate(
        provider=provider,
        model=hub.get_default_model(provider),
        prompt="What is the capital of France?"
    )
    print(f"{provider}: {response.text}")
```

## Development

### Setup

```bash
cd poc/model_hub
pip install -e ".[dev]"
```

### Testing

```bash
pytest tests/
```

### Adding New Providers

1. Create a new provider class inheriting from `BaseProvider`
2. Implement the required methods
3. Register the provider in the registry

```python
from model_hub.providers.base import BaseProvider

class MyProvider(BaseProvider):
    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        # Implementation here
        pass

# Register the provider
from model_hub.providers import ProviderRegistry
registry = ProviderRegistry()
registry.register("myprovider", MyProvider)
```

## API Reference

### ModelHub

Main interface for interacting with LLM providers.

#### Methods

- `generate(provider, model, prompt, **kwargs)` - Generate text
- `stream_generate(provider, model, prompt, **kwargs)` - Stream generation
- `list_providers()` - List available providers
- `get_default_model(provider)` - Get default model for provider
- `validate_config()` - Validate provider configurations

### Provider Interface

All providers implement the same interface:

```python
class BaseProvider(ABC):
    @abstractmethod
    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        pass

    @abstractmethod
    async def stream_generate(self, request: GenerateRequest):
        pass

    @abstractmethod
    def get_default_model(self) -> str:
        pass
```

## Error Handling

The hub provides consistent error handling:

```python
from model_hub.exceptions import ProviderError, ConfigurationError

try:
    response = await hub.generate("invalid_provider", "model", "prompt")
except ConfigurationError as e:
    print(f"Configuration error: {e}")
except ProviderError as e:
    print(f"Provider error: {e}")
```

## Performance Considerations

- Connection pooling for HTTP requests
- Response caching for identical requests
- Async/await for non-blocking operations
- Configurable timeouts and retries

## Security

- API keys stored in environment variables
- No sensitive data logging
- Input validation and sanitization
- Rate limiting support

## Future Enhancements

- Model fine-tuning support
- Batch processing
- Model comparison tools
- Cost tracking and optimization
- Model performance benchmarking
- Custom model deployment support

## Contributing

This is a proof of concept. For production use, consider:

- Comprehensive error handling
- Rate limiting and quota management
- Monitoring and observability
- Security audits
- Performance optimization
- Extensive testing

## License

MIT License
