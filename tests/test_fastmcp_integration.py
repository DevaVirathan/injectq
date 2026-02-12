"""Tests for the FastMCP integration module (injectq.integrations.fastmcp)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from injectq.integrations import fastmcp as mmod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class DummyContainer:
    """Minimal container stub that records get() calls."""

    def __init__(self) -> None:
        self.calls: list[type] = []
        self._services: dict[type, Any] = {}

    def register(self, tp: type, instance: Any) -> None:
        self._services[tp] = instance

    def get(self, tp: type) -> Any:
        self.calls.append(tp)
        return self._services.get(tp, tp)


class UserService:
    def get_users(self) -> list[str]:
        return ["alice", "bob"]


class OrderService:
    def get_orders(self) -> list[str]:
        return ["order-1"]


# ---------------------------------------------------------------------------
# get_container_mcp
# ---------------------------------------------------------------------------


def test_get_container_mcp_raises_when_no_context() -> None:
    """Should raise InjectionError if no container is set in ContextVar."""
    from injectq.utils import InjectionError

    # Ensure clean state
    token = mmod._mcp_container.set(None)
    try:
        with pytest.raises(InjectionError, match="No InjectQ container"):
            mmod.get_container_mcp()
    finally:
        mmod._mcp_container.reset(token)


def test_get_container_mcp_returns_container() -> None:
    """Should return the container set in the ContextVar."""
    container = DummyContainer()
    token = mmod._mcp_container.set(container)
    try:
        result = mmod.get_container_mcp()
        assert result is container
    finally:
        mmod._mcp_container.reset(token)


# ---------------------------------------------------------------------------
# InjectMCP
# ---------------------------------------------------------------------------


def test_inject_mcp_resolves_type() -> None:
    """InjectMCP should call container.get(interface) and return the result."""
    container = DummyContainer()
    svc = UserService()
    container.register(UserService, svc)

    token = mmod._mcp_container.set(container)
    try:
        result = mmod.InjectMCP(UserService)
        assert result is svc
        assert container.calls == [UserService]
    finally:
        mmod._mcp_container.reset(token)


def test_inject_mcp_multiple_types() -> None:
    """InjectMCP should resolve different types independently."""
    container = DummyContainer()
    user_svc = UserService()
    order_svc = OrderService()
    container.register(UserService, user_svc)
    container.register(OrderService, order_svc)

    token = mmod._mcp_container.set(container)
    try:
        r1 = mmod.InjectMCP(UserService)
        r2 = mmod.InjectMCP(OrderService)
        assert r1 is user_svc
        assert r2 is order_svc
        assert container.calls == [UserService, OrderService]
    finally:
        mmod._mcp_container.reset(token)


def test_inject_mcp_raises_without_context() -> None:
    """InjectMCP should raise when no container context is active."""
    from injectq.utils import InjectionError

    token = mmod._mcp_container.set(None)
    try:
        with pytest.raises(InjectionError):
            mmod.InjectMCP(UserService)
    finally:
        mmod._mcp_container.reset(token)


# ---------------------------------------------------------------------------
# InjectQMCPMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_middleware_sets_and_resets_context() -> None:
    """Middleware should set container in ContextVar and reset after call_next."""
    container = DummyContainer()
    middleware = mmod.InjectQMCPMiddleware(container=container)

    captured_container = None

    async def fake_call_next(context: Any) -> str:
        nonlocal captured_container
        captured_container = mmod._mcp_container.get()
        return "ok"

    # Before middleware: no container
    assert mmod._mcp_container.get() is None

    context = MagicMock()
    result = await middleware.on_message(context, fake_call_next)

    # During call_next, the container was set
    assert captured_container is container
    # After middleware, context is reset
    assert mmod._mcp_container.get() is None
    assert result == "ok"


@pytest.mark.asyncio
async def test_middleware_resets_on_exception() -> None:
    """Middleware must reset ContextVar even if call_next raises."""
    container = DummyContainer()
    middleware = mmod.InjectQMCPMiddleware(container=container)

    async def failing_call_next(context: Any) -> None:
        raise ValueError("boom")

    context = MagicMock()
    with pytest.raises(ValueError, match="boom"):
        await middleware.on_message(context, failing_call_next)

    # ContextVar must be reset
    assert mmod._mcp_container.get() is None


@pytest.mark.asyncio
async def test_middleware_nested_calls_isolate_context() -> None:
    """Nested middleware invocations should properly isolate context."""
    container_a = DummyContainer()
    container_b = DummyContainer()

    middleware_a = mmod.InjectQMCPMiddleware(container=container_a)
    middleware_b = mmod.InjectQMCPMiddleware(container=container_b)

    captured = []

    async def inner_call_next(context: Any) -> str:
        captured.append(mmod._mcp_container.get())
        return "inner"

    async def outer_call_next(context: Any) -> str:
        captured.append(mmod._mcp_container.get())
        # Simulate middleware_b running inside middleware_a
        result = await middleware_b.on_message(context, inner_call_next)
        # After inner middleware, outer container should be restored
        captured.append(mmod._mcp_container.get())
        return result

    context = MagicMock()
    await middleware_a.on_message(context, outer_call_next)

    assert captured[0] is container_a  # outer saw container_a
    assert captured[1] is container_b  # inner saw container_b
    assert captured[2] is container_a  # outer restored after inner


# ---------------------------------------------------------------------------
# setup_mcp
# ---------------------------------------------------------------------------


def test_setup_mcp_adds_middleware() -> None:
    """setup_mcp should call mcp.add_middleware with InjectQMCPMiddleware."""
    container = DummyContainer()
    mock_mcp = MagicMock()

    mmod.setup_mcp(container, mock_mcp)

    mock_mcp.add_middleware.assert_called_once()
    middleware = mock_mcp.add_middleware.call_args[0][0]
    assert isinstance(middleware, mmod.InjectQMCPMiddleware)
    assert middleware._container is container


def test_setup_mcp_raises_without_fastmcp(monkeypatch: Any) -> None:
    """setup_mcp should raise RuntimeError if fastmcp is not importable."""
    import importlib

    original_import = importlib.import_module

    def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "fastmcp":
            raise ImportError("no fastmcp")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", mock_import)

    container = DummyContainer()
    mock_mcp = MagicMock()

    with pytest.raises(RuntimeError, match="fastmcp"):
        mmod.setup_mcp(container, mock_mcp)


# ---------------------------------------------------------------------------
# End-to-end: simulated MCP tool call with DI
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_end_to_end_tool_with_injection() -> None:
    """Simulates a full MCP tool call where InjectMCP resolves a service."""
    container = DummyContainer()
    svc = UserService()
    container.register(UserService, svc)

    middleware = mmod.InjectQMCPMiddleware(container=container)

    async def tool_handler(context: Any) -> list[str]:
        # This is what an MCP tool function would do
        user_service = mmod.InjectMCP(UserService)
        return user_service.get_users()

    context = MagicMock()
    result = await middleware.on_message(context, tool_handler)
    assert result == ["alice", "bob"]
