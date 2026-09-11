import asyncio
import importlib
import unittest
from unittest.mock import patch


class ProviderDeadlineTests(unittest.IsolatedAsyncioTestCase):
    def runner(self):
        name = 'lrrk_litewing_ai.provider_deadline'
        self.assertIsNotNone(importlib.util.find_spec(name), 'provider deadline missing')
        return importlib.import_module(name).run_bounded

    async def test_deadline_cancels_inflight_operation(self):
        run = self.runner()
        cancelled = []
        async def operation():
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)
        with self.assertRaises(TimeoutError):
            await run(operation, timeout_s=.02)
        self.assertEqual(cancelled, [True])

    async def test_preexisting_stop_never_starts_operation(self):
        run = self.runner()
        calls = []
        async def operation():
            calls.append(True)
        with self.assertRaises(asyncio.CancelledError):
            await run(operation, timeout_s=1, stop=lambda: True)
        self.assertEqual(calls, [])

    async def test_returns_completed_result(self):
        run = self.runner()
        async def operation():
            return 'historical advice'
        self.assertEqual(await run(operation, timeout_s=1), 'historical advice')


@unittest.skipUnless(importlib.util.find_spec('agents'), 'optional Agents SDK unavailable')
class LivePromptDeadlineTests(unittest.TestCase):
    def test_cli_provider_cancels_hung_sdk_run(self):
        from lrrk_litewing_ai.cli import _live_prompt
        cancelled, turns = [], []
        async def hung(agent, prompt, **kwargs):
            turns.append(kwargs.get('max_turns'))
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)
        with patch('lrrk_litewing_ai.cli.create_assistant', return_value=object()):
            with patch('agents.Runner.run', new=hung):
                with self.assertRaises(TimeoutError):
                    _live_prompt(None, 'status', timeout_s=.02)
        self.assertEqual(cancelled, [True])
        self.assertEqual(turns, [4])
