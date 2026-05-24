"""Tests for LangChainInstrumentor.

LangChain 0.3.x uses register_configure_hook / ContextVar mechanism (not a
_global_callbacks list). These tests verify that:
  - patch() sets the ContextVar so the handler is included in new CallbackManagers
  - unpatch() clears the ContextVar so the handler is no longer included
  - double-patch() is idempotent (adds only one handler per CallbackManager)
  - the registered handler is a TraceCastCallback instance
"""

import pytest
from tracecast.instrumentors.langchain_inst import (
    LangChainInstrumentor,
    _tracecast_handler_var,
)


class TestLangChainInstrumentor:
    """Tests for the LangChainInstrumentor class."""

    def setup_method(self):
        """Ensure the ContextVar starts clean for every test."""
        self._ctx_token = _tracecast_handler_var.set(None)

    def teardown_method(self):
        """Restore the ContextVar after each test."""
        try:
            _tracecast_handler_var.reset(self._ctx_token)
        except ValueError:
            _tracecast_handler_var.set(None)

    # ------------------------------------------------------------------
    # State tests (no LangChain CallbackManager involved)
    # ------------------------------------------------------------------

    def test_initial_state(self):
        inst = LangChainInstrumentor()
        assert not inst.is_patched()
        assert inst._handler is None

    def test_patch_sets_is_patched(self):
        inst = LangChainInstrumentor()
        inst.patch()
        assert inst.is_patched()
        inst.unpatch()

    def test_unpatch_clears_is_patched(self):
        inst = LangChainInstrumentor()
        inst.patch()
        inst.unpatch()
        assert not inst.is_patched()
        assert inst._handler is None

    def test_idempotent_patch(self):
        """Calling patch() twice should not register a second handler."""
        inst = LangChainInstrumentor()
        inst.patch()
        first_handler = inst._handler
        inst.patch()  # no-op
        assert inst._handler is first_handler, "Handler should not change on second patch()"
        inst.unpatch()

    def test_idempotent_unpatch(self):
        """Calling unpatch() when not patched is a no-op."""
        inst = LangChainInstrumentor()
        inst.unpatch()  # should not raise
        assert not inst.is_patched()

    # ------------------------------------------------------------------
    # ContextVar integration tests
    # ------------------------------------------------------------------

    def test_patch_sets_context_var(self):
        """After patch(), the ContextVar should hold the handler."""
        inst = LangChainInstrumentor()
        assert _tracecast_handler_var.get() is None
        inst.patch()
        assert _tracecast_handler_var.get() is inst._handler
        inst.unpatch()

    def test_unpatch_clears_context_var(self):
        """After unpatch(), the ContextVar should be None."""
        inst = LangChainInstrumentor()
        inst.patch()
        inst.unpatch()
        assert _tracecast_handler_var.get() is None

    def test_handler_is_tracecast_callback(self):
        """The registered handler must be a TraceCastCallback instance."""
        from tracecast.integrations.langchain import TraceCastCallback

        inst = LangChainInstrumentor()
        inst.patch()
        assert isinstance(inst._handler, TraceCastCallback)
        inst.unpatch()

    # ------------------------------------------------------------------
    # Full CallbackManager integration tests
    # ------------------------------------------------------------------

    def test_patch_adds_handler_to_callback_manager(self):
        """After patch(), a new CallbackManager should include our handler."""
        from langchain_core.callbacks.manager import CallbackManager

        inst = LangChainInstrumentor()
        inst.patch()

        cm = CallbackManager.configure()
        handler_ids = [id(h) for h in cm.handlers]
        assert id(inst._handler) in handler_ids, (
            "TraceCastCallback should be present in CallbackManager after patch()"
        )
        inst.unpatch()

    def test_unpatch_removes_handler_from_callback_manager(self):
        """After unpatch(), new CallbackManagers should NOT include our handler."""
        from langchain_core.callbacks.manager import CallbackManager

        inst = LangChainInstrumentor()
        inst.patch()
        handler_ref = inst._handler
        inst.unpatch()

        cm = CallbackManager.configure()
        handler_ids = [id(h) for h in cm.handlers]
        assert id(handler_ref) not in handler_ids, (
            "TraceCastCallback should NOT be present in CallbackManager after unpatch()"
        )

    def test_idempotent_patch_single_handler_in_callback_manager(self):
        """Calling patch() twice should result in exactly one handler in CallbackManager."""
        from langchain_core.callbacks.manager import CallbackManager
        from tracecast.integrations.langchain import TraceCastCallback

        inst = LangChainInstrumentor()
        inst.patch()
        inst.patch()  # no-op

        cm = CallbackManager.configure()
        tracecast_handlers = [h for h in cm.handlers if isinstance(h, TraceCastCallback)]
        assert len(tracecast_handlers) == 1, (
            f"Expected exactly 1 TraceCastCallback, found {len(tracecast_handlers)}"
        )
        inst.unpatch()

    def test_multiple_instances_independent(self):
        """Two independent instrumentor instances should each manage their own state."""
        inst1 = LangChainInstrumentor()
        inst2 = LangChainInstrumentor()

        inst1.patch()
        assert inst1.is_patched()
        assert not inst2.is_patched()

        # unpatch inst1 — inst2 unaffected
        inst1.unpatch()
        assert not inst1.is_patched()
        assert not inst2.is_patched()
