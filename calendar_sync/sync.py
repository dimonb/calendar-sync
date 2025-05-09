import logging

from datetime import datetime, timezone
from calendar_sync.db.session import get_session
from calendar_sync.db.models import EventMapping
from calendar_sync.config import yaml_config
from calendar_sync.utils.time import get_time_window
from calendar_sync.utils.env import load_env
from calendar_sync.calendars.base import BaseCalendar
from opentelemetry import trace


logger = logging.getLogger(__name__)
tracer = trace.get_tracer("calendar-sync")


def load_calendars():
    with tracer.start_as_current_span("sync.load_calendars"):
        calendars = []
        for calendar_cfg in yaml_config.get("calendars", []):
            calendars.append(BaseCalendar.get_calendar(calendar_cfg))
        return calendars

def process_busy_event(event, source, session):
    summary = event.get("summary", "")
    if summary.lower().strip() != "busy":
        return False
    if source.onlysource:
        return True
    start = event.get("start")
    end = event.get("end")
    logger.info(f"Busy event: {event.get('id')} {start} - {end}")
    mapping = session.query(EventMapping).filter_by(
        target_calendar=source.id,
        busy_event_id=event["id"],
    ).first()
    if not mapping:
        logger.info(f"Deleting orphan busy event {event['id']} in {source.id}")
        with tracer.start_as_current_span(
            "sync.delete_orphan_busy_event",
            attributes={"target_calendar": source.id, "busy_event_id": event["id"]},
        ):
            try:
                source.delete_event(event["id"])
            except Exception:
                logger.exception(f"Failed to delete orphan busy event {event['id']} in {source.id}")
    return True

def process_single_event_for_target(event, source, target, session, failed_calendars):
    start = event["start"]
    end = event["end"]
    logger.info(
        f"Processing event {event['id']}: {start} → {end} | {event.get('summary','')[:30]} for target {target.id}"
    )
    try:
        mapping = session.query(EventMapping).filter_by(
            source_calendar=source.id,
            source_event_id=event["id"],
            target_calendar=target.id,
        ).first()
        if not mapping:
            logger.info(f"Creating busy event in {target.id} for source event {event['id']}")
            with tracer.start_as_current_span(
                "sync.create_busy_event",
                attributes={"target_calendar": target.id, "source_event_id": event["id"]},
            ):
                busy_event_id = target.create_busy_event(start, end, source_event_id=event["id"])
            new_mapping = EventMapping(
                source_calendar=source.id,
                source_event_id=event["id"],
                target_calendar=target.id,
                busy_event_id=busy_event_id,
                last_synced_time=datetime.now(timezone.utc),
                start_time=start,
                end_time=end,
            )
            session.add(new_mapping)
            session.commit()
        elif mapping.start_time != start or mapping.end_time != end:
            logger.info(f"Event {event['id']} changed, deleting old busy and recreating")
            # delete old busy event
            try:
                with tracer.start_as_current_span(
                    "sync.delete_old_busy_event",
                    attributes={"target_calendar": target.id, "busy_event_id": mapping.busy_event_id},
                ):
                    target.delete_event(mapping.busy_event_id)
            except Exception:
                logger.exception("Failed to delete old busy event before update")
            # create updated busy event
            try:
                with tracer.start_as_current_span(
                    "sync.update_busy_event",
                    attributes={"target_calendar": target.id, "source_event_id": event["id"]},
                ):
                    busy_event_id = target.create_busy_event(start, end, source_event_id=event["id"])
                mapping.busy_event_id = busy_event_id
                mapping.start_time = start
                mapping.end_time = end
                mapping.last_synced_time = datetime.now(timezone.utc)
                session.commit()
            except Exception:
                logger.exception(f"Failed to recreate busy event in {target.id}")
        else:
            logger.debug(f"Busy event already exists for {event['id']} in {target.id}")
    except Exception:
        logger.exception(f"Failed to create busy event in {target.id}")
        failed_calendars.add(target.id)

def cleanup_orphans(source, calendars, session, existing_ids):
    stored = session.query(EventMapping).filter_by(source_calendar=source.id).all()
    for mapping in stored:
        if mapping.source_event_id in existing_ids or source.onlysource:
            continue
        logger.info(f"Deleting orphan busy event {mapping.busy_event_id} from {source.id}")
        try:
            target_cal = next(c for c in calendars if c.id == mapping.target_calendar)
            with tracer.start_as_current_span(
                "sync.delete_orphan_busy_event",
                attributes={"target_calendar": target_cal.id, "busy_event_id": mapping.busy_event_id},
            ):
                target_cal.delete_event(mapping.busy_event_id)
            session.delete(mapping)
            session.commit()
        except Exception:
            logger.exception(f"Failed to delete orphan busy event {mapping.busy_event_id} in {source.id}")

def process_source(source, calendars, session, time_min, time_max, failed_calendars):
    with tracer.start_as_current_span(
        "sync.fetch_events",
        attributes={"source_calendar": source.id, "time_min": time_min, "time_max": time_max},
    ):
        logger.info(f"Fetching events from calendar: {source.id}")
        try:
            events = source.list_events(time_min, time_max)
            logger.info(f"Fetched {len(events)} events from {source.id}")
        except Exception:
            logger.exception(f"Failed to fetch events from {source.id}")
            return

    ids = set()
    for event in events:
        event_id = event.get("id")
        ids.add(event_id)
        with tracer.start_as_current_span(
            "sync.process_event",
            attributes={
                "source_calendar": source.id,
                "event_id": event_id,
                "event_summary": event.get("summary", "")[:80],
            },
        ):
            summary = event.get("summary", "")
            if not summary:
                logger.info(
                    f"Skipping event: {event_id} {event.get('start')} - {event.get('end')} due to missing summary"
                )
                continue
            if process_busy_event(event, source, session):
                continue
            if "T" not in event.get("start", "") or "T" not in event.get("end", ""):
                logger.info(
                    f"Skipping all-day event: {event_id} {event.get('start')} - {event.get('end')}"
                )
                continue
            for target in calendars:
                if target == source or target.onlysource or target.id in failed_calendars:
                    continue
                process_single_event_for_target(event, source, target, session, failed_calendars)

    cleanup_orphans(source, calendars, session, ids)

def main():
    with tracer.start_as_current_span("calendar-sync.run"):
        load_env()
        logger.info("Starting calendar sync service...")
        session = get_session()

        calendars = load_calendars()

        if not calendars:
            logger.error("No calendars configured. Exiting.")
            return

        time_min, time_max = get_time_window(days=yaml_config.get("sync_window_days", 3))
        logger.info(f"Sync window: {time_min} to {time_max}")

        failed_calendars = set()

        for source in calendars:
            with tracer.start_as_current_span(
                "sync.process_source",
                attributes={"source_calendar": source.id},
            ):
                process_source(source, calendars, session, time_min, time_max, failed_calendars)

        if failed_calendars:
            logger.error(
                f"Failed to create busy events for calendars: {', '.join(failed_calendars)}"
            )
        else:
            logger.info("Calendar sync completed successfully.")
