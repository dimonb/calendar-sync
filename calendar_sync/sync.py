import os
import yaml
import logging
from datetime import datetime, timezone
from calendar_sync.db.session import get_session
from calendar_sync.db.models import EventMapping
from calendar_sync.utils.time import get_time_window
from calendar_sync.utils.env import load_env
from calendar_sync.calendars.base import BaseCalendar

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

def load_config():
    config_path = os.getenv('CONFIG_PATH', '/app/config.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def load_calendars(config):
    calendars = []
    for calendar_cfg in config.get('calendars', []):
        calendars.append(BaseCalendar.get_calendar(calendar_cfg))
    return calendars

def main():
    load_env()
    logger.info("Starting calendar sync service...")
    config = load_config()
    session = get_session()

    calendars = load_calendars(config)

    if not calendars:
        logger.error("No calendars configured. Exiting.")
        return

    time_min, time_max = get_time_window(days=config.get('sync_window_days', 3))
    logger.info(f"Sync window: {time_min} to {time_max}")

    failed_calendars = set()

    for source in calendars:
        logger.info(f"Fetching events from calendar: {source.id}")
        try:
            events = source.list_events(time_min, time_max)
            logger.info(f"Fetched {len(events)} events from {source.id}")
        except Exception:
            logger.exception(f"Failed to fetch events from {source.id}")
            continue

        ids = set()
        for event in events:
            start = event['start']
            end = event['end']
            summary = event.get('summary', '')
            ids.add(event['id'])

            if not summary:
                logger.info(f"Skipping event: {event.get('id')} {start} - {end} due to missing summary")
                continue

            if summary.lower().strip() == 'busy':
                logger.info(f"Busy event: {event.get('id')} {start} - {end}")
                mapping = session.query(EventMapping).filter_by(
                    target_calendar=source.id,
                    busy_event_id=event['id']
                ).first()
                if not mapping:
                    logger.info(f"Deleting orphan busy event {event['id']} in {source.id}")
                    try:
                        source.delete_event(event['id'])
                    except Exception:
                        logger.exception(f"Failed to delete orphan busy event {event['id']} in {source.id}")
                continue
            
            if 'T' not in start or 'T' not in end:
                logger.info(f"Skipping all-day event: {event.get('id')} {start} - {end}")
                continue

            for target in calendars:
                if target == source:
                    continue

                if target.onlysource:
                    continue

                if target.id in failed_calendars:
                    logger.info(f"Skipping failed calendar: {target.id}")
                    continue

                logger.info(f"Processing event {event['id']}: {start} → {end} | {summary[:30]} for target {target.id}")

                try:
                    mapping = session.query(EventMapping).filter_by(
                        source_calendar=source.id,
                        source_event_id=event['id'],
                        target_calendar=target.id
                    ).first()

                    if not mapping:
                        logger.info(f"Creating busy event in {target.id} for source event {event['id']}")
                        busy_event_id = target.create_busy_event(start, end, source_event_id=event['id'])
                        new_mapping = EventMapping(
                            source_calendar=source.id,
                            source_event_id=event['id'],
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
                        try:
                            target.delete_event(mapping.busy_event_id)
                        except Exception:
                            logger.exception(f"Failed to delete old busy event before update")

                        try:
                            busy_event_id = target.create_busy_event(start, end, source_event_id=event['id'])
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
    
        stored_events = session.query(EventMapping).filter_by(
            source_calendar=source.id
        ).all()

        for event in stored_events:
            if event.source_event_id not in ids:
                logger.info(f"Deleting orphan busy event {event.busy_event_id} from {source.id}")
                try:
                    d_cal = [c for c in calendars if c.id == event.target_calendar][0]
                    d_cal.delete_event(event.busy_event_id)
                    session.delete(event)
                    session.commit()
                except Exception:
                    logger.exception(f"Failed to delete orphan busy event {event.busy_event_id} in {source.id}")

    if failed_calendars:
        logger.error(f"Failed to create busy events for calendars: {', '.join(failed_calendars)}")
    else:
        logger.info("Calendar sync completed successfully.")

if __name__ == "__main__":
    main()
