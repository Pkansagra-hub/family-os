#!/usr/bin/env python3
"""
Example usage of the Model Hub POC.
"""

import asyncio

from model_hub import ModelHub


async def main():
    """Demonstrate Model Hub usage."""

    # Set up environment variables for providers
    # Uncomment and set your API keys:
    # os.environ["OPENAI_API_KEY"] = "your-openai-key"
    # os.environ["ANTHROPIC_API_KEY"] = "your-anthropic-key"
    # os.environ["GOOGLE_API_KEY"] = "your-google-key"

    print("🚀 Model Hub POC Demo")
    print("=" * 50)

    async with ModelHub() as hub:
        # List available providers
        providers = hub.list_providers()
        print(f"📋 Configured providers: {providers}")

        if not providers:
            print(
                "❌ No providers configured. Please set API keys in environment variables."
            )
            print("   Example: OPENAI_API_KEY=your_key python example.py")
            return

        # Test each provider
        test_prompt = "Explain quantum computing in 3 sentences."

        for provider in providers:
            try:
                print(f"\n🤖 Testing {provider.upper()}...")

                # Get default model
                model = hub.get_default_model(provider)
                print(f"   Using model: {model}")

                # Generate response
                response = await hub.generate(
                    provider=provider,
                    prompt=test_prompt,
                    max_tokens=150,
                    temperature=0.7,
                )

                print(f"   Response: {response.text[:100]}...")
                print(f"   Tokens: {response.usage.total_tokens}")
                print(f"   ✅ {provider.upper()} working!")

            except Exception as e:
                print(f"   ❌ {provider.upper()} failed: {e}")

        # Demonstrate streaming (if OpenAI is available)
        if "openai" in providers:
            print("\n🌊 Streaming demo with OpenAI...")
            try:
                chunks = []
                async for chunk in hub.stream_generate(
                    provider="openai", prompt="Write a haiku about AI.", max_tokens=50
                ):
                    chunks.append(chunk.text)
                    print(chunk.text, end="", flush=True)

                print(f"\n   📊 Collected {len(chunks)} chunks")

            except Exception as e:
                print(f"   ❌ Streaming failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
