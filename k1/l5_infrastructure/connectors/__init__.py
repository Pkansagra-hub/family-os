"""
Layer 5 - Connectors Module

This module provides K0 connection lifecycle management for the K1-K0 bridge,
including HTTP/2 connection pooling, health checks, and auto-reconnection.

Components:
- k0_connector: K0 connection lifecycle manager

K0 Connection Architecture (ADR-0001a, ADR-0044):
- HTTP/2 persistent connections (TLS 1.3)
- Connection pool: 5 connections (command, query, SSE, observability, health)
- Health check: Ping K0 every 10s
- Auto-reconnection: Exponential backoff (1s→2s→4s→8s→30s max)
- Keep-alive: 60s timeout
- Connection reuse: >90% hit rate target

K0 Ports:
- Command Port: :5200 (write operations, CQRS command)
- Query Port: :5201 (read operations, multi-store retrieval)
- SSE Port: :5202 (server-sent events, real-time updates)
- Observability Port: :5203 (metrics/logs push)

Connection Lifecycle:
1. Establish: TLS 1.3 handshake, HTTP/2 negotiation (<100ms)
2. Active: Keep-alive pings every 10s, connection pool ready
3. Health Check: Ping K0 every 10s, detect failures <30s
4. Reconnect: Exponential backoff on failure (1s→2s→4s→8s→30s max)
5. Shutdown: Graceful connection closure, drain in-flight requests

Performance (ADR-0024):
- Connection establishment: <100ms P95
- Reconnection latency: 1s-30s (exponential backoff)
- Connection pool hit rate: >90%
- Health check: 10s interval, <10ms latency

Primary ADRs:
- ADR-0001a: K0 Bridge Architecture (connection management)
- ADR-0044: K0 Bridge HTTP/2 (bridge client)
- ADR-0044a: Transport Protocol (connection health, auto-reconnect)

Research Foundation:
- HTTP/2 connection pooling (multiplexing, persistent connections)
- TLS 1.3 (modern encryption, 0-RTT resumption)
- Exponential backoff (Ethernet collision avoidance, AWS retry guidance)
"""

# __all__ = [
#     "K0Connector",
# ]
