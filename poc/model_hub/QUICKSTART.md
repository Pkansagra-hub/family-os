# Model Hub POC - Quick Start Guide

## ✅ Module Status

The **Model Hub POC** is now fully functional and ready to use! All syntax errors have been fixed and the module imports successfully.

## 📦 What Was Fixed

1. **Syntax errors** in provider files (anthropic.py, google.py, local.py)
2. **Module import paths** - renamed `types.py` to `model_types.py` to avoid conflicts
3. **Duplicate code** - removed duplicate method definitions
4. **File structure** - ensured proper package initialization

## 🚀 Quick Start

### 1. Import the Module

```python
from poc.model_hub import ModelHub, ProviderRegistry
from poc.model_hub.exceptions import ProviderError, ConfigurationError
```

### 2. Initialize ModelHub

```python
# Create a ModelHub instance
hub = ModelHub()

# List available providers
providers = hub.list_providers()
print(f"Available providers: {providers}")
```

### 3. Configure Providers

Set environment variables for your LLM providers:

```bash
# OpenAI
export OPENAI_API_KEY=sk-your-key
export OPENAI_DEFAULT_MODEL=gpt-4

# Anthropic
export ANTHROPIC_API_KEY=sk-ant-your-key
export ANTHROPIC_DEFAULT_MODEL=claude-3-sonnet-20240229

# Google AI
export GOOGLE_API_KEY=your-google-key
export GOOGLE_DEFAULT_MODEL=gemini-pro

# Local Models
export LOCAL_DEFAULT_MODEL=microsoft/DialoGPT-medium
```

### 4. Use the Module

```python
import asyncio
from poc.model_hub import ModelHub

async def main():
    async with ModelHub() as hub:
        # Generate text
        response = await hub.generate(
            provider="openai",
            model="gpt-4",
            prompt="Explain quantum computing",
            max_tokens=200
        )
        print(response.text)

# Run
asyncio.run(main())
```

## 🧪 Testing

Run the comprehensive test suite:

```bash
cd d:\familyos
python test_model_hub_comprehensive.py
```

Expected output:
```
============================================================
🧪 Model Hub POC - Comprehensive Test Suite
============================================================
Testing imports...
✅ All imports successful!
...
🎉 All tests passed!
```

## 📋 Available Providers

| Provider | Status | Models |
|----------|--------|--------|
| OpenAI | ✅ Ready | GPT-4, GPT-3.5-turbo, etc. |
| Anthropic | ✅ Ready | Claude 3 Opus, Sonnet, Haiku |
| Google AI | ✅ Ready | Gemini Pro |
| Local (HF) | ✅ Ready | DialoGPT, Falcon, etc. |

## 🔌 Module Structure

```
poc/model_hub/
├── __init__.py                 # Package init (exports ModelHub, ProviderRegistry)
├── hub.py                      # Main ModelHub class
├── config.py                   # Configuration management
├── exceptions.py               # Custom exceptions
├── model_types.py             # Type definitions
├── providers/
│   ├── base.py                # Base provider interface
│   ├── openai.py              # OpenAI implementation
│   ├── anthropic.py           # Anthropic implementation
│   ├── google.py              # Google implementation
│   └── local.py               # Local model implementation
└── README.md                   # Full documentation
```

## 💡 Key Features

- **Unified Interface**: Single API for all providers
- **Type Safe**: Full type hints with Pydantic
- **Async Support**: Native async/await
- **Error Handling**: Comprehensive exception hierarchy
- **Extensible**: Easy to add new providers
- **Configuration**: Environment-based setup

## 🔧 Common Tasks

### List Available Providers

```python
hub = ModelHub()
print(hub.list_providers())  # ['openai', 'anthropic', 'google', 'local']
```

### Get Default Model

```python
model = hub.get_default_model("openai")
print(model)  # gpt-4
```

### Stream Generation

```python
async for chunk in hub.stream_generate(
    provider="openai",
    prompt="Write a poem",
    max_tokens=100
):
    print(chunk.text, end="", flush=True)
```

### Handle Errors

```python
from poc.model_hub.exceptions import ProviderError, ConfigurationError

try:
    response = await hub.generate("invalid_provider", prompt="test")
except ProviderError as e:
    print(f"Provider error: {e}")
except ConfigurationError as e:
    print(f"Config error: {e}")
```

## 📖 Complete Example

```python
import asyncio
from poc.model_hub import ModelHub

async def main():
    """Complete example using Model Hub."""

    # Initialize hub
    hub = ModelHub()

    # Show configured providers
    providers = hub.list_providers()
    print(f"Configured providers: {providers}")

    if "openai" in providers:
        # Generate text with OpenAI
        print("\n🤖 Using OpenAI...")
        response = await hub.generate(
            provider="openai",
            prompt="What is machine learning?",
            temperature=0.7,
            max_tokens=200
        )
        print(f"Response: {response.text}")
        print(f"Tokens used: {response.usage.total_tokens}")

        # Stream generation
        print("\n🌊 Streaming with OpenAI...")
        async for chunk in hub.stream_generate(
            provider="openai",
            prompt="Write a haiku about AI",
            max_tokens=50
        ):
            print(chunk.text, end="", flush=True)
        print()

    # Close connections
    await hub.close()

# Run the example
asyncio.run(main())
```

## 🎓 Next Steps

1. Set your API keys in environment variables
2. Import the module: `from poc.model_hub import ModelHub`
3. Create a ModelHub instance: `hub = ModelHub()`
4. Generate text with your preferred provider
5. Explore the different providers and models

## ❓ Troubleshooting

### Import Error
```python
# ❌ Don't do this (from model_hub folder)
from model_hub import ModelHub

# ✅ Do this (from familyos root)
from poc.model_hub import ModelHub
```

### No Providers Found
- Check environment variables are set correctly
- Verify API keys in `.env.example`
- Run: `python -c "from poc.model_hub.config import config; print(config.list_configured_providers())"`

### Provider Error
- Ensure API key is correct
- Check rate limits
- Try with a different model

## 📚 Documentation

See `poc/model_hub/README.md` for comprehensive documentation.

---

**Status**: ✅ Fully Functional
**Last Updated**: 2025-11-07
**Version**: 0.1.0
