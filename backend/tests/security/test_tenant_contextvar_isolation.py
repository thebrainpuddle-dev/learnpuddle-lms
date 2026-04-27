# tests/security/test_tenant_contextvar_isolation.py
"""
Regression tests — Fix 1: Tenant context uses contextvars.ContextVar (ASGI-safe).

The original implementation used threading.local() which leaks state across
coroutines that share a thread in ASGI. contextvars.ContextVar is coroutine-aware:
each asyncio Task gets its own copy of context variables inherited at creation time.

These tests prove:
1. get_current_tenant() returns None in a fresh context (safe default).
2. Concurrent asyncio tasks see only their own tenant (no cross-task leak).
3. copy_context() child does not pollute the parent's contextvar.
4. Sequential context runs are fully independent.
"""

import asyncio
import contextvars
from django.test import TestCase

from utils.tenant_middleware import (
    _current_tenant,
    get_current_tenant,
    set_current_tenant,
    clear_current_tenant,
)


# ---------------------------------------------------------------------------
# Lightweight mock tenant objects (no DB required for pure contextvar tests)
# ---------------------------------------------------------------------------

class _MockTenant:
    """Minimal tenant stand-in for contextvar tests that don't need the ORM."""
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"<MockTenant name={self.name!r}>"


# ===========================================================================
# 1. Default value
# ===========================================================================

class ContextVarDefaultTestCase(TestCase):
    """get_current_tenant() must return None in a context where it was never set."""

    def tearDown(self):
        clear_current_tenant()

    def test_default_is_none_in_fresh_context(self):
        """
        A brand-new test context (or any context where set_current_tenant was
        never called) must return None — there must be no implicit global tenant.
        """
        clear_current_tenant()
        self.assertIsNone(get_current_tenant())

    def test_default_is_none_via_contextvar_get(self):
        """Direct ContextVar.get() also returns None by default."""
        clear_current_tenant()
        self.assertIsNone(_current_tenant.get())

    def test_set_then_clear_restores_none(self):
        """After set + clear, the value is back to None."""
        tenant = _MockTenant("SetClear")
        set_current_tenant(tenant)
        self.assertIs(get_current_tenant(), tenant)
        clear_current_tenant()
        self.assertIsNone(get_current_tenant())


# ===========================================================================
# 2. copy_context() child isolation (synchronous)
# ===========================================================================

class CopyContextIsolationTestCase(TestCase):
    """
    contextvars.copy_context() creates a snapshot of the current context.
    A child context.run() operates in its own copy — mutations in the child
    must NOT bleed back into the parent.
    """

    def tearDown(self):
        clear_current_tenant()

    def test_child_context_mutation_does_not_affect_parent(self):
        """
        Parent sets tenant A. Child (copy_context) sets tenant B.
        After child.run(), parent still sees tenant A.
        """
        tenant_a = _MockTenant("ParentA")
        tenant_b = _MockTenant("ChildB")

        set_current_tenant(tenant_a)

        child_ctx = contextvars.copy_context()
        child_result = {}

        def child_work():
            _current_tenant.set(tenant_b)
            child_result["seen"] = get_current_tenant()

        child_ctx.run(child_work)

        # Child saw tenant B
        self.assertIs(child_result["seen"], tenant_b)

        # Parent still sees tenant A (the key regression guard)
        self.assertIs(
            get_current_tenant(),
            tenant_a,
            "Parent context must not be affected by child's set_current_tenant()",
        )

    def test_two_independent_child_contexts_do_not_cross_bleed(self):
        """
        Two sibling child contexts each set a different tenant.
        Each sees only its own value; parent sees its own (None).
        """
        clear_current_tenant()

        tenant_a = _MockTenant("SiblingA")
        tenant_b = _MockTenant("SiblingB")

        ctx_a = contextvars.copy_context()
        ctx_b = contextvars.copy_context()

        results = {}

        def work_a():
            _current_tenant.set(tenant_a)
            results["a"] = get_current_tenant()

        def work_b():
            _current_tenant.set(tenant_b)
            results["b"] = get_current_tenant()

        ctx_a.run(work_a)
        ctx_b.run(work_b)

        self.assertIs(results["a"], tenant_a)
        self.assertIs(results["b"], tenant_b)

        # Parent context is untouched
        self.assertIsNone(
            get_current_tenant(),
            "Parent context must remain None after sibling contexts ran",
        )

    def test_nested_child_contexts_fully_isolated(self):
        """
        Grandparent → child → grandchild: each level sees its own value,
        mutations at any level don't propagate upward.
        """
        tenant_gp = _MockTenant("Grandparent")
        tenant_child = _MockTenant("Child")
        tenant_gc = _MockTenant("Grandchild")

        set_current_tenant(tenant_gp)

        child_ctx = contextvars.copy_context()
        grandchild_result = {}
        child_result = {}

        def child_work():
            _current_tenant.set(tenant_child)
            child_result["before"] = get_current_tenant()

            gc_ctx = contextvars.copy_context()

            def gc_work():
                _current_tenant.set(tenant_gc)
                grandchild_result["seen"] = get_current_tenant()

            gc_ctx.run(gc_work)
            child_result["after"] = get_current_tenant()

        child_ctx.run(child_work)

        self.assertIs(child_result["before"], tenant_child)
        self.assertIs(child_result["after"], tenant_child, "Child not affected by grandchild")
        self.assertIs(grandchild_result["seen"], tenant_gc)
        self.assertIs(get_current_tenant(), tenant_gp, "Grandparent unaffected")


# ===========================================================================
# 3. asyncio.gather() concurrent task isolation
# ===========================================================================

class AsyncioConcurrentContextVarTestCase(TestCase):
    """
    asyncio Tasks each inherit an independent copy of the context at creation
    time.  Mutations inside a task are invisible to other tasks and the parent.

    This is the core ASGI regression: under threading.local(), concurrent
    requests on the same thread would overwrite each other's tenant.
    """

    def tearDown(self):
        clear_current_tenant()

    def _run(self, coro):
        """Run an async coroutine to completion in a new event loop."""
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_concurrent_tasks_see_own_tenant_not_other(self):
        """
        Two concurrent tasks each set their own tenant via ContextVar.
        Each task reads back its own tenant — no cross-task leak.
        """
        tenant_a = _MockTenant("AsyncA")
        tenant_b = _MockTenant("AsyncB")

        async def task_a(result_box):
            _current_tenant.set(tenant_a)
            await asyncio.sleep(0)          # yield — lets task_b run
            result_box.append(get_current_tenant())

        async def task_b(result_box):
            _current_tenant.set(tenant_b)
            await asyncio.sleep(0)
            result_box.append(get_current_tenant())

        async def main():
            results_a = []
            results_b = []
            await asyncio.gather(
                task_a(results_a),
                task_b(results_b),
            )
            return results_a, results_b

        results_a, results_b = self._run(main())

        self.assertEqual(len(results_a), 1)
        self.assertEqual(len(results_b), 1)

        self.assertIs(
            results_a[0],
            tenant_a,
            "Task A must see tenant_a, not tenant_b (threading.local regression guard)",
        )
        self.assertIs(
            results_b[0],
            tenant_b,
            "Task B must see tenant_b, not tenant_a",
        )

    def test_many_concurrent_tasks_each_see_own_tenant(self):
        """
        Ten concurrent tasks, each assigned a unique mock tenant.
        Every task must read back exactly its own tenant after yielding.
        """
        n = 10
        mock_tenants = [_MockTenant(f"Tenant-{i}") for i in range(n)]

        async def worker(tenant, result_box):
            _current_tenant.set(tenant)
            await asyncio.sleep(0)  # interleave with other tasks
            result_box[tenant.name] = get_current_tenant()

        async def main():
            results = {}
            coros = [worker(t, results) for t in mock_tenants]
            await asyncio.gather(*coros)
            return results

        results = self._run(main())

        for tenant in mock_tenants:
            self.assertIs(
                results.get(tenant.name),
                tenant,
                f"Task for {tenant.name} read back wrong tenant",
            )

    def test_parent_context_unaffected_by_child_tasks(self):
        """
        Spawning tasks that set their own tenants must not alter the
        event-loop's 'parent' context (where no tenant is set).
        """
        clear_current_tenant()
        tenant_in_task = _MockTenant("TaskOnly")

        async def task():
            _current_tenant.set(tenant_in_task)
            await asyncio.sleep(0)

        async def main():
            parent_before = get_current_tenant()
            await asyncio.gather(task())
            parent_after = get_current_tenant()
            return parent_before, parent_after

        before, after = self._run(main())

        self.assertIsNone(before, "Parent context must start as None")
        self.assertIsNone(after, "Parent context must remain None after tasks complete")

    def test_context_var_used_not_threading_local(self):
        """
        Structural guard: the _current_tenant attribute exposed by the module
        must be a contextvars.ContextVar, NOT threading.local().
        This fails immediately if someone reverts the ASGI-safety fix.
        """
        self.assertIsInstance(
            _current_tenant,
            contextvars.ContextVar,
            "_current_tenant must be contextvars.ContextVar, not threading.local(). "
            "Revert of the ASGI-safety fix detected.",
        )
