from datetime import datetime, timezone

from career_os.workflow_scheduler import LocalWorkflowScheduler, ScheduleSpec


def test_scheduler_dispatches_due_schedule(tmp_path):
    scheduler = LocalWorkflowScheduler(state_dir=tmp_path, tick_sec=1)
    scheduler.register(ScheduleSpec("career", "0 8,20 * * *", "Asia/Kolkata", "skip"))
    calls = []
    scheduler.set_dispatcher(lambda workflow_id, payload: calls.append((workflow_id, payload)))
    now = datetime(2026, 8, 21, 8, 0, tzinfo=timezone.utc)
    scheduler.tick(now)
    assert calls == []


def test_scheduler_rejects_invalid_overlap_policy(tmp_path):
    scheduler = LocalWorkflowScheduler(state_dir=tmp_path)
    try:
        scheduler.register(ScheduleSpec("career", "0 8 * * *", "Asia/Kolkata", "bad"))
    except ValueError as exc:
        assert "overlap_policy" in str(exc)
    else:
        raise AssertionError("invalid overlap policy accepted")


def test_scheduler_persists_state(tmp_path):
    scheduler = LocalWorkflowScheduler(state_dir=tmp_path)
    scheduler.state.data["schedules"]["career"] = {"last_scheduled_at": "2026-08-21T08:00:00+05:30"}
    scheduler.state.save()
    restored = LocalWorkflowScheduler(state_dir=tmp_path)
    assert restored.state.data["schedules"]["career"]["last_scheduled_at"].startswith("2026-08-21")
