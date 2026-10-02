import pytest
from unittest.mock import MagicMock

from bot.modules.taskm import build_taskm_view, _get_task_details
from bot import user_data, task_dict, non_queued_dl, queued_dl
from bot.helper.ext_utils.task_manager import check_running_tasks, start_from_queued


def test_get_task_details_empty():
    running, queued = _get_task_details(12345)
    assert running == []
    assert queued == []


def test_build_taskm_view():
    mock_user = MagicMock()
    mock_user.id = 12345
    mock_user.mention.return_value = "User123"

    user_data[12345] = {"maxtask": 2}

    text, buttons = build_taskm_view(12345, mock_user)
    assert "Task Manager" in text
    assert "Configured Task Limit:</b> <b>2</b>" in text
    assert buttons is not None


@pytest.mark.asyncio
async def test_user_limit_and_queue_advancement():
    user_id = 99999
    user_data[user_id] = {"maxtask": 1}

    # Mock listener
    listener1 = MagicMock()
    listener1.user_id = user_id
    listener1.mid = 10001
    listener1.force_run = False
    listener1.force_upload = False
    listener1.force_download = False

    listener2 = MagicMock()
    listener2.user_id = user_id
    listener2.mid = 10002
    listener2.force_run = False
    listener2.force_upload = False
    listener2.force_download = False

    # Mock tasks
    task1 = MagicMock()
    task1.listener = listener1
    task1.name.return_value = "Task 1"
    task1.gid.return_value = "gid1"

    task2 = MagicMock()
    task2.listener = listener2
    task2.name.return_value = "Task 2"
    task2.gid.return_value = "gid2"

    task_dict[10001] = task1
    task_dict[10002] = task2

    # Task 1 check
    over1, evt1 = await check_running_tasks(listener1, "dl")
    assert not over1
    assert 10001 in non_queued_dl

    # Task 2 check (limit = 1, so should be queued)
    over2, evt2 = await check_running_tasks(listener2, "dl")
    assert bool(over2) is True
    assert 10002 in queued_dl

    # Simulate Task 1 finish
    non_queued_dl.remove(10001)
    del task_dict[10001]

    # Run queue advancement
    await start_from_queued()

    # Task 2 should now be unqueued
    assert 10002 in non_queued_dl
    assert 10002 not in queued_dl

    # Clean up
    if 10002 in non_queued_dl:
        non_queued_dl.remove(10002)
    task_dict.pop(10002, None)
    user_data.pop(user_id, None)
