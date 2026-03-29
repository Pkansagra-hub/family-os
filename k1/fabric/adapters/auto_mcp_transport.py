"""
k1.fabric.adapters.auto_mcp_transport -- Auto-discovering MCP transport.

Convention-based replacement for LiveMCPTransport. Scans
``k1/tools/mcp_servers/`` at construction time and auto-registers
all discovered servers. No hardcoded routing tables.

Adding a new MCP server requires ZERO changes to this file or any
other Fabric code:

  1. Create ``k1/tools/mcp_servers/<name>/server.py``
  2. Add YAML contract(s) in ``k1/contracts/tools/``
  3. Done.

Two server patterns are detected automatically:

  **JSON-RPC** (Calendar, Weather style):
    ``server.py`` exports a class whose name ends with ``MCPServer``
    that has a ``handle_message(msg)`` coroutine, and a module-level
    ``TOOLS`` list declaring tool names.

  **FastMCP** (Notes, Recipes style):
    ``server.py`` exports a ``FastMCP`` instance (any attribute name).
    Tool functions registered with ``@mcp.tool()`` are extracted.
    Function names are matched after stripping the ``tool.<verb>.``
    prefix from the Fabric capability name.

Internal/meta handlers (build_agent, discover_capabilities, etc.)
that need Fabric context are registered via ``register_handler()``.

Implements IMCPTransport structurally.
"""

from __future__ import annotations

import importlib
import inspect
import json
import logging
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from k1.fabric.providers.mcp_provider import MCPRequest, MCPResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Server pattern descriptors
# ---------------------------------------------------------------------------


class _JSONRPCServer:
    """Wrapper around a JSON-RPC style MCP server instance."""

    __slots__ = ("instance", "tool_names")

    def __init__(self, instance: Any, tool_names: List[str]) -> None:
        self.instance = instance
        self.tool_names = tool_names


class _FastMCPServer:
    """Wrapper around discovered FastMCP tool functions."""

    __slots__ = ("functions",)

    def __init__(self) -> None:
        # short_name -> async callable
        self.functions: Dict[str, Callable[..., Any]] = {}


# ---------------------------------------------------------------------------
# AutoDiscoveryMCPTransport
# ---------------------------------------------------------------------------


class AutoDiscoveryMCPTransport:
    """
    Auto-discovering MCP transport.

    Scans ``servers_dir`` for MCP server modules and builds a routing
    table without any hardcoded tool->server mappings.

    Implements IMCPTransport:
      - async send(request) -> MCPResponse
      - async ping() -> bool
      - is_connected() -> bool
      - async close() -> None
    """

    def __init__(
        self,
        servers_dir: str = "k1/tools/mcp_servers",
        *,
        auto_discover: bool = True,
    ) -> None:
        self._connected = True

        # tool_name (full) -> JSON-RPC server instance
        self._jsonrpc_routes: Dict[str, Any] = {}
        # short function name -> async callable
        self._fastmcp_routes: Dict[str, Callable[..., Any]] = {}
        # tool_name (full) -> async callable  (for internal handlers)
        self._handler_routes: Dict[str, Callable[..., Awaitable[MCPResponse]]] = {}
        # Servers that need cleanup
        self._closeable: List[Any] = []

        if auto_discover:
            self._discover_servers(Path(servers_dir))

        logger.info(
            "[AutoDiscoveryMCPTransport] Discovered %d JSON-RPC tools, "
            "%d FastMCP tools, %d handler tools",
            len(self._jsonrpc_routes),
            len(self._fastmcp_routes),
            len(self._handler_routes),
        )

    # ------------------------------------------------------------------
    # Public: register internal/meta handlers post-construction
    # ------------------------------------------------------------------

    def register_handler(
        self,
        tool_name: str,
        handler: Callable[..., Awaitable[MCPResponse]],
    ) -> None:
        """
        Register an internal handler for a tool name.

        Use this for meta-tools (build_agent, discover_capabilities,
        find_prompts) that need Fabric context and cannot be
        auto-discovered from the filesystem.

        Args:
            tool_name: Full Fabric capability name
                (e.g. ``tool.write.build_agent``).
            handler: Async callable ``(MCPRequest) -> MCPResponse``.
        """
        self._handler_routes[tool_name] = handler
        logger.debug(
            "[AutoDiscoveryMCPTransport] Registered handler: %s",
            tool_name,
        )

    # ------------------------------------------------------------------
    # IMCPTransport protocol
    # ------------------------------------------------------------------

    async def send(self, request: MCPRequest) -> MCPResponse:
        """
        Route an MCP request to the correct server.

        Dispatch priority:
          1. Explicit handlers (build_agent, discover, find_prompts)
          2. JSON-RPC servers (full tool name match)
          3. FastMCP tools (short name match after prefix strip)
          4. Unknown -> error response
        """
        start = time.monotonic()
        tool_name = request.tool_name

        # Strip Fabric metadata from arguments
        clean_args = {k: v for k, v in request.arguments.items() if not k.startswith("_")}
        clean_request = MCPRequest(
            method=request.method,
            tool_name=request.tool_name,
            arguments=clean_args,
            timeout_ms=request.timeout_ms,
            trace_id=request.trace_id,
        )

        # 1. Explicit handlers
        handler = self._handler_routes.get(tool_name)
        if handler is not None:
            try:
                return await handler(clean_request)
            except Exception as exc:
                elapsed = int((time.monotonic() - start) * 1000)
                logger.error(
                    "[AutoDiscoveryMCPTransport] Handler error for %s: %s",
                    tool_name,
                    exc,
                )
                return MCPResponse(
                    success=False,
                    error_message=str(exc),
                    latency_ms=elapsed,
                )

        # 2. JSON-RPC servers
        server = self._jsonrpc_routes.get(tool_name)
        if server is not None:
            return await self._call_jsonrpc(server, clean_request, start)

        # 3. FastMCP tools (strip tool.<verb>. prefix)
        short_name = self._strip_tool_prefix(tool_name)
        func = self._fastmcp_routes.get(short_name)
        if func is not None:
            return await self._call_fastmcp(func, clean_request, start)

        # 4. Unknown
        elapsed = int((time.monotonic() - start) * 1000)
        logger.warning("[AutoDiscoveryMCPTransport] Unknown tool: %s", tool_name)
        return MCPResponse(
            success=False,
            error_message=f"Unknown tool: {tool_name}",
            latency_ms=elapsed,
        )

    async def ping(self) -> bool:
        """Always reachable (in-process)."""
        return self._connected

    def is_connected(self) -> bool:
        """Check if transport is connected."""
        return self._connected

    async def close(self) -> None:
        """Clean up all server resources."""
        self._connected = False
        for server in self._closeable:
            close_fn = getattr(server, "close", None)
            if close_fn:
                try:
                    if inspect.iscoroutinefunction(close_fn):
                        await close_fn()
                    else:
                        close_fn()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Discovery engine
    # ------------------------------------------------------------------

    def _discover_servers(self, servers_dir: Path) -> None:
        """
        Scan servers_dir for MCP server modules.

        Each subdirectory with a ``server.py`` is imported and
        inspected for either the JSON-RPC or FastMCP pattern.
        """
        if not servers_dir.exists():
            logger.warning(
                "[AutoDiscoveryMCPTransport] Servers dir not found: %s",
                servers_dir,
            )
            return

        for child in sorted(servers_dir.iterdir()):
            if not child.is_dir() or child.name.startswith("_"):
                continue
            server_py = child / "server.py"
            if not server_py.exists():
                continue

            server_name = child.name
            module_path = f"k1.tools.mcp_servers.{server_name}.server"

            try:
                module = importlib.import_module(module_path)
            except Exception as exc:
                logger.warning(
                    "[AutoDiscoveryMCPTransport] Failed to import %s: %s",
                    module_path,
                    exc,
                )
                continue

            # Try JSON-RPC pattern first
            if self._try_register_jsonrpc(module, server_name):
                continue

            # Try FastMCP pattern
            if self._try_register_fastmcp(module, server_name):
                continue

            logger.debug(
                "[AutoDiscoveryMCPTransport] No recognized pattern in %s",
                module_path,
            )

    def _try_register_jsonrpc(self, module: Any, server_name: str) -> bool:
        """
        Detect and register a JSON-RPC style server.

        Looks for:
          - Module-level ``TOOLS`` list with tool definitions
          - A class ending with ``MCPServer`` that has ``handle_message``
        """
        tools_list = getattr(module, "TOOLS", None)
        if not tools_list or not isinstance(tools_list, list):
            return False

        server_cls = self._find_server_class(module)
        if server_cls is None:
            return False

        server = self._safe_instantiate(server_cls, server_name)
        if server is None:
            return False

        # Register each tool from TOOLS list
        registered = 0
        for tool_def in tools_list:
            name = tool_def.get("name", "")
            if name:
                self._jsonrpc_routes[name] = server
                registered += 1

        if registered > 0:
            self._closeable.append(server)
            logger.info(
                "[AutoDiscoveryMCPTransport] Registered JSON-RPC server '%s' " "with %d tools",
                server_name,
                registered,
            )
            return True

        return False

    def _try_register_fastmcp(self, module: Any, server_name: str) -> bool:
        """
        Detect and register a FastMCP style server.

        Looks for a FastMCP instance in the module. Extracts
        registered tool functions and maps them by function name.
        """
        mcp_instance = self._find_fastmcp_instance(module)
        if mcp_instance is None:
            return False

        # Call create_server() if available (initializes storage etc.)
        create_fn = getattr(module, "create_server", None)
        if create_fn and callable(create_fn):
            try:
                create_fn()
            except Exception as exc:
                logger.warning(
                    "[AutoDiscoveryMCPTransport] create_server() failed for %s: %s",
                    server_name,
                    exc,
                )

        # Extract tool functions from FastMCP._tool_manager or _tools
        tools = self._extract_fastmcp_tools(mcp_instance)
        if not tools:
            return False

        registered = 0
        for func_name, func in tools:
            self._fastmcp_routes[func_name] = func
            registered += 1

        if registered > 0:
            logger.info(
                "[AutoDiscoveryMCPTransport] Registered FastMCP server '%s' " "with %d tools: %s",
                server_name,
                registered,
                list(t[0] for t in tools),
            )
            return True

        return False

    # ------------------------------------------------------------------
    # Helpers: class/instance detection
    # ------------------------------------------------------------------

    @staticmethod
    def _find_server_class(module: Any) -> Optional[type]:
        """Find a class ending with 'MCPServer' that has handle_message."""
        for attr_name in dir(module):
            obj = getattr(module, attr_name, None)
            if (
                isinstance(obj, type)
                and attr_name.endswith("MCPServer")
                and hasattr(obj, "handle_message")
            ):
                return obj
        return None

    @staticmethod
    def _find_fastmcp_instance(module: Any) -> Optional[Any]:
        """Find a FastMCP instance in a module."""
        # Check common names first
        for name in ("mcp", "server", "app"):
            obj = getattr(module, name, None)
            if obj is not None and _is_fastmcp(obj):
                return obj

        # Fall back to scanning all attributes
        for attr_name in dir(module):
            if attr_name.startswith("_"):
                continue
            obj = getattr(module, attr_name, None)
            if obj is not None and _is_fastmcp(obj):
                return obj

        return None

    @staticmethod
    def _safe_instantiate(server_cls: type, server_name: str) -> Optional[Any]:
        """
        Instantiate a server class, trying common constructor patterns.

        Tries in order:
          1. cls(db_path=":memory:")  -- servers with storage
          2. cls()                    -- servers without args
        """
        # Try with db_path (for servers that use SQLite storage)
        try:
            return server_cls(db_path=":memory:")
        except TypeError:
            pass

        # Try with no args
        try:
            return server_cls()
        except Exception as exc:
            logger.warning(
                "[AutoDiscoveryMCPTransport] Cannot instantiate %s.%s: %s",
                server_name,
                server_cls.__name__,
                exc,
            )
            return None

    @staticmethod
    def _extract_fastmcp_tools(
        mcp_instance: Any,
    ) -> List[Tuple[str, Callable[..., Any]]]:
        """
        Extract tool functions from a FastMCP instance.

        FastMCP stores tools in _tool_manager.tools (dict of name -> Tool)
        or _tools (older versions). Each Tool has .fn (the raw function).
        """
        tools: List[Tuple[str, Callable[..., Any]]] = []

        # Try _tool_manager.tools (FastMCP >= 2.x)
        tool_mgr = getattr(mcp_instance, "_tool_manager", None)
        if tool_mgr is not None:
            tool_dict = getattr(tool_mgr, "_tools", None) or getattr(tool_mgr, "tools", {})
            if isinstance(tool_dict, dict):
                for name, tool_obj in tool_dict.items():
                    fn = getattr(tool_obj, "fn", tool_obj)
                    tools.append((name, fn))
                if tools:
                    return tools

        # Try _tools directly (older FastMCP)
        tool_dict = getattr(mcp_instance, "_tools", None)
        if isinstance(tool_dict, dict):
            for name, tool_obj in tool_dict.items():
                fn = getattr(tool_obj, "fn", tool_obj)
                tools.append((name, fn))
            if tools:
                return tools

        # Try .list_tools() if it exists (sync version)
        list_fn = getattr(mcp_instance, "list_tools", None)
        if list_fn and callable(list_fn):
            try:
                raw = list_fn()
                if isinstance(raw, dict):
                    for name, tool_obj in raw.items():
                        fn = getattr(tool_obj, "fn", tool_obj)
                        tools.append((name, fn))
            except Exception:
                pass

        return tools

    @staticmethod
    def _strip_tool_prefix(tool_name: str) -> str:
        """
        Strip ``tool.<verb>.`` prefix from a capability name.

        ``tool.read.notes_list`` -> ``notes_list``
        ``tool.write.recipe_meal_plan`` -> ``recipe_meal_plan``
        ``tool.execute.date_calc`` -> ``date_calc``
        """
        parts = tool_name.split(".", 2)
        if len(parts) == 3 and parts[0] == "tool":
            return parts[2]
        return tool_name

    # ------------------------------------------------------------------
    # Dispatch: JSON-RPC
    # ------------------------------------------------------------------

    async def _call_jsonrpc(
        self,
        server: Any,
        request: MCPRequest,
        start: float,
    ) -> MCPResponse:
        """Call a JSON-RPC MCP server via handle_message."""
        message = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": request.tool_name,
                "arguments": dict(request.arguments),
            },
        }

        try:
            response = await server.handle_message(message)
            elapsed = int((time.monotonic() - start) * 1000)

            if "error" in response:
                return MCPResponse(
                    success=False,
                    error_message=response["error"].get("message", "Unknown error"),
                    latency_ms=elapsed,
                    raw=response,
                )

            result = response.get("result", {})
            content = result.get("content", [])

            return MCPResponse(
                success=True,
                content=content,
                latency_ms=elapsed,
                raw=response,
            )

        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.error(
                "[AutoDiscoveryMCPTransport] JSON-RPC error for %s: %s",
                request.tool_name,
                exc,
            )
            return MCPResponse(
                success=False,
                error_message=str(exc),
                latency_ms=elapsed,
            )

    # ------------------------------------------------------------------
    # Dispatch: FastMCP
    # ------------------------------------------------------------------

    async def _call_fastmcp(
        self,
        func: Callable[..., Any],
        request: MCPRequest,
        start: float,
    ) -> MCPResponse:
        """Call a FastMCP tool function directly."""
        try:
            result = await func(**request.arguments)
            elapsed = int((time.monotonic() - start) * 1000)

            text = json.dumps(result, default=str)
            return MCPResponse(
                success=True,
                content=[{"type": "text", "text": text}],
                latency_ms=elapsed,
            )

        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.error(
                "[AutoDiscoveryMCPTransport] FastMCP error for %s: %s",
                request.tool_name,
                exc,
            )
            return MCPResponse(
                success=False,
                error_message=str(exc),
                latency_ms=elapsed,
            )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _is_fastmcp(obj: Any) -> bool:
    """Check if an object is a FastMCP instance (duck-typed)."""
    # Avoid import of fastmcp at module level -- detect structurally
    cls_name = type(obj).__name__
    if cls_name == "FastMCP":
        return True
    # Duck-type: has tool() decorator and run() method
    return hasattr(obj, "tool") and hasattr(obj, "run") and callable(getattr(obj, "tool", None))
