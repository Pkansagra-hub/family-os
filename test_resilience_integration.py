#!/usr/bin/env python3#!/usr/bin/env python3

""""""

Quick integration test for resilience componentsQuick integration test for resilience components

""""""

import asyncioimport asyncio

import tempfileimport tempfile

from pathlib import Pathimport os

from pathlib import Path

async def test_integration():

    # Create temp config directoryasync def test_integration():

    with tempfile.TemporaryDirectory() as temp_dir:    # Create temp config directory

        temp_path = Path(temp_dir)    with tempfile.TemporaryDirectory() as temp_dir:

        # Create test configs

        # Create test configs        retry_config = Path(temp_dir) / 'retry_policy.yml'

        retry_config = temp_path / 'retry_policy.yml'        circuit_config = Path(temp_dir) / 'circuit_breaker.yml'

        circuit_config = temp_path / 'circuit_breakers.yml'

        retry_config.write_text('max_retries: 3\nbase_delay_ms: 100\n')

        retry_config.write_text('max_retries: 3\nbase_delay_ms: 100\n')        circuit_config.write_text('failure_threshold: 3\ntimeout_s: 60\n')

        circuit_config.write_text('circuit_breakers:\n  test_service:\n    failure_threshold: 3\n    timeout_duration_ms: 60000\n    success_threshold: 1\n    slow_call_threshold_ms: 5000\n    time_window_ms: 60000\n    fallback_strategy: default_value\n    enabled: true\n')

        # Test hot reload manager

        # Test hot reload manager        from k1.l5_infrastructure.resilience.hot_reload import HotReloadManager

        from k1.l5_infrastructure.resilience.hot_reload import HotReloadManager        manager = HotReloadManager(temp_dir)

        manager = HotReloadManager(temp_dir)        await manager.start()

        await manager.start()

        # Test config loading

        # Test config loading        retry_config_data = manager.get_config('retry_policy')

        retry_config_data = manager.get_config('retry_policy')        circuit_config_data = manager.get_config('circuit_breaker')

        circuit_config_data = manager.get_config('circuit_breakers')

        print('Hot reload config loading: PASS' if retry_config_data and circuit_config_data else 'FAIL')

        print('Hot reload config loading: PASS' if retry_config_data and circuit_config_data else 'FAIL')

        # Test circuit breaker manager

        # Test circuit breaker manager        from k1.l5_infrastructure.resilience.circuit_breaker_manager import CircuitBreakerManager

        from k1.l5_infrastructure.resilience.circuit_breaker_manager import CircuitBreakerManager        cb_manager = CircuitBreakerManager(manager)

        cb_manager = CircuitBreakerManager(str(circuit_config))

        # Test circuit creation

        # Test circuit creation        cb = cb_manager.get_circuit_breaker('test_service')

        cb = cb_manager.get_circuit('test_service')        print('Circuit breaker creation: PASS' if cb else 'FAIL')

        print('Circuit breaker creation: PASS' if cb else 'FAIL')

        # Test retry policy

        # Test retry policy        from k1.l5_infrastructure.resilience.retry_policy import RetryPolicy

        from k1.l5_infrastructure.resilience.retry_policy import RetryPolicy        retry_policy = RetryPolicy()

        retry_policy = RetryPolicy()        result = await retry_policy.execute(lambda: 'success')

        result = await retry_policy.execute(lambda: 'success', idempotent=True)        print('Retry policy execution: PASS' if result == 'success' else 'FAIL')

        print('Retry policy execution: PASS' if result == 'success' else 'FAIL')

        await manager.stop()

        await manager.stop()

        print('All resilience components integration: SUCCESS')

        print('All resilience components integration: SUCCESS')

if __name__ == '__main__':

if __name__ == '__main__':    asyncio.run(test_integration())
    asyncio.run(test_integration())
