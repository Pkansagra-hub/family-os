"""Vertex AI / Agent Platform provider plugin.

Uses the Google Gen AI SDK for Gemini models on the Google Cloud / Agent
Platform endpoint family (``aiplatform.googleapis.com``), not the Gemini
Developer API endpoint (``generativelanguage.googleapis.com``).

Managed open/partner models that expose the Vertex OpenAI-compatible Chat
Completions endpoint, such as xAI Grok (``xai/...``), are routed through
``/endpoints/openapi/chat/completions``.

Auth modes supported by the SDK:
  - ADC / service account credentials, recommended for production.
  - Google Cloud API key, useful for local testing.

Runtime env accepted:
  - GOOGLE_GENAI_USE_VERTEXAI=True
  - GOOGLE_CLOUD_PROJECT or legacy GOOGLE_PROJECT_ID
  - GOOGLE_CLOUD_LOCATION or legacy GOOGLE_LOCATION
  - optional GOOGLE_API_KEY for Cloud API-key auth
  - optional VERTEX_MODEL to override the manifest-selected model
"""

from __future__ import annotations

import os
from dataclasses import replace
from typing import Any

from k1.model_hub.plugins.base import NormalizedRequest
from k1.model_hub.plugins.google_plugin import GooglePlugin
from k1.model_hub.plugins.openai_plugin import OpenAIPlugin
from k1.model_hub.types import ProviderError

_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_openapi_model(model_id: str) -> bool:
    normalized = (model_id or "").strip().lower()
    return normalized.startswith("xai/") or normalized.startswith("grok-")


def _openapi_model_id(model_id: str) -> str:
    normalized = (model_id or "").strip()
    if normalized.lower().startswith("grok-"):
        return f"xai/{normalized}"
    return normalized


class _VertexOpenAICompatPlugin(OpenAIPlugin):
    """OpenAI-compatible Vertex MaaS adapter used for partner models."""

    provider_id = "vertex"

    def __init__(self, owner: "VertexPlugin") -> None:
        super().__init__()
        self._owner = owner

    def _auth_headers(self, request: NormalizedRequest | None = None) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._owner._openapi_access_token()}"}

    def _build_chat_body(self, request: NormalizedRequest, *, stream: bool) -> dict[str, Any]:
        is_reasoning = self._is_reasoning_model(request.model_id)
        messages = self._format_messages(request, is_reasoning=is_reasoning)
        body: dict[str, Any] = {
            "model": request.model_id,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "stream": stream,
        }
        if not is_reasoning:
            body["temperature"] = request.temperature
        if request.tools:
            body["tools"] = [{"type": "function", "function": tool} for tool in request.tools]
            if request.tool_choice:
                body["tool_choice"] = request.tool_choice
        if request.output_schema:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "schema": request.output_schema,
                },
            }
        if request.extra.get("response_format"):
            body["response_format"] = request.extra["response_format"]
        if request.extra.get("web_search_options"):
            body["web_search_options"] = request.extra["web_search_options"]
        return body

    def _format_messages(
        self,
        request: NormalizedRequest,
        is_reasoning: bool,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        for message in request.messages:
            entry: dict[str, Any] = {"role": message.role, "content": message.content}
            if message.tool_call_id:
                entry["tool_call_id"] = message.tool_call_id
            if message.name:
                entry["name"] = message.name
            messages.append(entry)
        return messages

    def _is_reasoning_model(self, model_id: str) -> bool:
        return model_id.strip().lower().endswith("-reasoning") or super()._is_reasoning_model(
            model_id
        )


class VertexPlugin(GooglePlugin):
    """Google Cloud Vertex provider for Gemini and managed partner models."""

    provider_id = "vertex"

    def __init__(self) -> None:
        super().__init__()
        self._openai_compat = _VertexOpenAICompatPlugin(self)
        self._openapi_credentials: Any = None

    def _requires_api_key(self) -> bool:
        return False

    async def initialize(self, manifest: Any) -> None:
        await super().initialize(manifest)
        await self._openai_compat.initialize(manifest)

    async def close(self) -> None:
        await super().close()
        await self._openai_compat.close()

    async def execute(self, request: NormalizedRequest):
        model_id = self._resolve_model_id(request)
        if _is_openapi_model(model_id):
            openapi_request = self._as_openapi_request(request, model_id)
            self._openai_compat._api_base = self._openapi_base_url(model_id)
            return await self._openai_compat.execute(openapi_request)
        return await super().execute(request)

    async def stream_execute(self, request: NormalizedRequest):
        model_id = self._resolve_model_id(request)
        if _is_openapi_model(model_id):
            openapi_request = self._as_openapi_request(request, model_id)
            self._openai_compat._api_base = self._openapi_base_url(model_id)
            async for chunk in self._openai_compat.stream_execute(openapi_request):
                yield chunk
            return
        async for chunk in super().stream_execute(request):
            yield chunk

    def _create_client(self, genai: Any, types: Any) -> Any:
        project, location = self._resolve_project_location()
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project)
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", location)

        kwargs: dict[str, Any] = {
            "vertexai": True,
            "project": project,
            "location": location,
            "http_options": types.HttpOptions(
                api_version=os.environ.get("GOOGLE_GENAI_API_VERSION", "v1")
            ),
        }
        if self._api_key:
            kwargs["api_key"] = self._api_key
        return genai.Client(**kwargs)

    def _resolve_model_id(self, request: NormalizedRequest) -> str:
        return (
            os.environ.get("VERTEX_MODEL")
            or os.environ.get("GOOGLE_CLOUD_MODEL")
            or request.model_id
        )

    def _as_openapi_request(self, request: NormalizedRequest, model_id: str) -> NormalizedRequest:
        return replace(
            request,
            model_id=_openapi_model_id(model_id),
            reasoning_effort=None,
        )

    def _openapi_base_url(self, model_id: str) -> str:
        project, location = self._resolve_project_location()
        if _is_openapi_model(model_id) and not _truthy(os.environ.get("VERTEX_XAI_ALLOW_REGIONAL")):
            location = "global"
        host = "aiplatform.googleapis.com"
        if location != "global":
            host = f"{location}-aiplatform.googleapis.com"
        return f"https://{host}/v1/projects/{project}/locations/{location}/endpoints/openapi"

    def _openapi_access_token(self) -> str:
        explicit = (
            os.environ.get("VERTEX_OPENAI_ACCESS_TOKEN")
            or os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN")
            or os.environ.get("GOOGLE_CLOUD_ACCESS_TOKEN")
        )
        if explicit:
            return explicit
        try:
            import google.auth
            import google.auth.transport.requests
        except ImportError as exc:
            raise ProviderError(
                "Vertex OpenAI-compatible models require google-auth for ADC tokens.",
                provider_id=self.provider_id,
            ) from exc

        if self._openapi_credentials is None:
            self._openapi_credentials, _ = google.auth.default(scopes=[_CLOUD_PLATFORM_SCOPE])
        if not self._openapi_credentials.valid:
            self._openapi_credentials.refresh(google.auth.transport.requests.Request())
        token = getattr(self._openapi_credentials, "token", None)
        if not token:
            raise ProviderError(
                "Vertex OpenAI-compatible models require ADC OAuth credentials. "
                "Run: gcloud auth application-default login",
                provider_id=self.provider_id,
            )
        return str(token)

    def _resolve_project_location(self) -> tuple[str, str]:
        project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GOOGLE_PROJECT_ID")
        location = (
            os.environ.get("GOOGLE_CLOUD_LOCATION") or os.environ.get("GOOGLE_LOCATION") or "global"
        )
        if not project:
            raise ProviderError(
                "Vertex provider requires GOOGLE_CLOUD_PROJECT or GOOGLE_PROJECT_ID.",
                provider_id=self.provider_id,
            )
        return project, location


__all__ = ["VertexPlugin"]
