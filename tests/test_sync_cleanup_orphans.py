import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from calendar_sync.db.models import Base, EventMapping
from calendar_sync.sync import cleanup_orphans


class FakeCalendar:
    """Minimal stand-in for a calendar backend: only what cleanup_orphans touches."""

    def __init__(self, cal_id, onlysource=False, delete_error=None):
        self.id = cal_id
        self.onlysource = onlysource
        self.delete_error = delete_error
        self.deleted = []

    def delete_event(self, event_id):
        if self.delete_error:
            raise self.delete_error
        self.deleted.append(event_id)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def add_mapping(session, source_calendar, target_calendar, busy_event_id="busy-1"):
    now = datetime.datetime.now(datetime.UTC).isoformat()
    session.add(EventMapping(
        source_calendar=source_calendar,
        source_event_id="gone-event",
        target_calendar=target_calendar,
        busy_event_id=busy_event_id,
        start_time=now,
        end_time=now,
    ))
    session.commit()


def test_orphan_busy_event_is_deleted_from_its_target_calendar(session):
    source = FakeCalendar("src")
    target = FakeCalendar("dst")
    add_mapping(session, source_calendar="src", target_calendar="dst")

    cleanup_orphans(source, [source, target], session, existing_ids=set())

    assert target.deleted == ["busy-1"]
    assert session.query(EventMapping).count() == 0


def test_orphan_mapping_is_dropped_when_target_calendar_is_no_longer_configured(session):
    source = FakeCalendar("src")
    add_mapping(session, source_calendar="src", target_calendar="deleted-account")

    cleanup_orphans(
        source, [source], session, existing_ids=set(), configured_ids={"src"}
    )

    assert session.query(EventMapping).count() == 0


def test_orphan_mapping_is_kept_when_configured_target_failed_to_load(session):
    source = FakeCalendar("src")
    add_mapping(session, source_calendar="src", target_calendar="flaky")

    cleanup_orphans(
        source, [source], session, existing_ids=set(), configured_ids={"src", "flaky"}
    )

    assert session.query(EventMapping).count() == 1


def test_orphan_mapping_is_kept_when_the_remote_delete_fails(session):
    source = FakeCalendar("src")
    target = FakeCalendar("dst", delete_error=RuntimeError("api down"))
    add_mapping(session, source_calendar="src", target_calendar="dst")

    cleanup_orphans(source, [source, target], session, existing_ids=set())

    assert session.query(EventMapping).count() == 1
