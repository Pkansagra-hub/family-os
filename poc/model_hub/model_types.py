"""
Type definitions for the Model Hub.
"""

from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class ProviderType(str, Enum):
    """Supported provider types."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    GROQ = "groq"
    LOCAL = "local"
    CUSTOM = "custom"


class MessageRole(str, Enum):
    """Message roles for chat completions."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    """A chat message."""

    role: MessageRole
    content: str
    name: Optional[str] = None


class Usage(BaseModel):
    """Token usage information."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class GenerateRequest(BaseModel):
    """Request for text generation."""

    prompt: str
    model: str
    max_tokens: Optional[int] = None
    temperature: Optional[float] = Field(default=1.0, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=1.0, ge=0.0, le=1.0)
    top_k: Optional[int] = Field(default=None, ge=1)
    stop: Optional[Union[str, List[str]]] = None
    stream: bool = False
    messages: Optional[List[Message]] = None  # For chat completions
    system_prompt: Optional[str] = None
    extra_params: Optional[Dict[str, Any]] = None


class GenerateResponse(BaseModel):
    """Response from text generation."""

    text: str
    model: str
    provider: str
    usage: Usage
    finish_reason: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None


class StreamChunk(BaseModel):
    """A chunk of streaming response."""

    text: str
    model: str
    provider: str
    finish_reason: Optional[str] = None


class ProviderConfig(BaseModel):
    """Configuration for a provider."""

    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout: float = 30.0
    max_retries: int = 3
    default_model: Optional[str] = None
    extra_config: Optional[Dict[str, Any]] = None


class ModelInfo(BaseModel):
    """Information about a model."""

    name: str
    provider: str
    context_window: Optional[int] = None
    max_tokens: Optional[int] = None
    supports_streaming: bool = True
    supports_chat: bool = True
    input_cost_per_token: Optional[float] = None
    output_cost_per_token: Optional[float] = None
    extra_info: Optional[Dict[str, Any]] = None


# Type aliases
ProviderName = str
ModelName = str
AsyncStreamIterator = AsyncIterator[StreamChunk]
