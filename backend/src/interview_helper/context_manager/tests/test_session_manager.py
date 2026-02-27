from interview_helper.context_manager.database import PersistentDatabase
from interview_helper.ai_analysis.ai_analysis import FakeAnalyzer
from ulid import ULID
from interview_helper.context_manager.types import ProjectId, UserId
import pytest
import anyio

from interview_helper.context_manager.types import ResourceKey
from interview_helper.context_manager.session_context_manager import AppContextManager

pytestmark = pytest.mark.anyio


async def test_context_manager_maintains_individual_state():
    test_resource_key = ResourceKey[str]("string")
    contextManager1 = AppContextManager(
        (), ai_processer=FakeAnalyzer, db=PersistentDatabase.new_in_memory()
    )
    contextManager2 = AppContextManager(
        (), ai_processer=FakeAnalyzer, db=PersistentDatabase.new_in_memory()
    )

    project_id = ProjectId(ULID())

    ctx = await contextManager1.new_session(UserId(ULID()), project_id)

    with pytest.raises(AssertionError):
        # Not a valid context for contextManager2
        await contextManager2.register(ctx.session_id, test_resource_key, "hello")

    await ctx.register(test_resource_key, "hello")

    assert await ctx.get(test_resource_key) == "hello"


async def test_content_manager_can_wait():
    test_resource_key1 = ResourceKey[str]("string")
    test_resource_key2 = ResourceKey[str]("string2")
    context_manager = AppContextManager(
        (), ai_processer=FakeAnalyzer, db=PersistentDatabase.new_in_memory()
    )
    project_id = ProjectId(ULID())

    ctx = await context_manager.new_session(UserId(ULID()), project_id)

    got = {}

    event = anyio.Event()

    with anyio.move_on_after(1):
        async with anyio.create_task_group() as tg:

            async def waiter(got: dict[str, str]):
                event.set()
                got["val"] = await ctx.get_or_wait(test_resource_key2)

            tg.start_soon(waiter, got)

            # Wait for function
            await event.wait()

            # Ensure that Context Manager still functions normally
            str1 = "hello1"
            await ctx.register(test_resource_key1, str1)
            assert await ctx.get(test_resource_key1) == str1

            str2 = "hello2"
            await ctx.register(test_resource_key2, str2)

    # Exiting the TaskGroup waits for waiter to finish.
    assert got["val"] == "hello2"

    # Ensure that the context is unregistered properly
    await context_manager.teardown_session(ctx.session_id)

    # Can't access session anymore! It is unregistered
    with pytest.raises(AssertionError):
        await ctx.get(test_resource_key1)


async def test_content_manager_basic_can_wait():
    test_resource_key1 = ResourceKey[str]("string")
    context_manager = AppContextManager(
        (), ai_processer=FakeAnalyzer, db=PersistentDatabase.new_in_memory()
    )
    project_id = ProjectId(ULID())
    ctx = await context_manager.new_session(UserId(ULID()), project_id)

    # Test basic get_and_wait
    await ctx.register(test_resource_key1, "hello1")
    assert await ctx.get_or_wait(test_resource_key1) == "hello1"


async def test_get_settings():
    cm = AppContextManager(
        (), ai_processer=FakeAnalyzer, db=PersistentDatabase.new_in_memory()
    )

    # Ensure that this causes an error so we don't inadvertently use it in tests
    with pytest.raises(AssertionError):
        cm.get_settings()
