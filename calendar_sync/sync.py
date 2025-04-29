import os
import yaml
import logging
from datetime import datetime, timezone
from calendar_sync.db.session import get_session
from calendar_sync.db.models import EventMapping
from calendar_sync.calendars.google_calendar import GoogleCalendar
from calendar_sync.calendars.outlook_calendar import OutlookCalendar
from calendar_sync.calendars.caldav_calendar import CaldavCalendar
from calendar_sync.utils.time import get_time_window
from calendar_sync.utils.env import load_env

# Настройка логов
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
        if calendar_cfg['type'] == 'google':
            calendars.append(GoogleCalendar(
                calendar_id=calendar_cfg['id'],
                credentials_path=calendar_cfg.get('credentials_path'),
                token_path=calendar_cfg.get('token_path')
            ))
        elif calendar_cfg['type'] == 'outlook':
            calendars.append(OutlookCalendar(calendar_cfg['id']))
        elif calendar_cfg['type'] == 'caldav':
            calendars.append(CaldavCalendar(
                url=calendar_cfg['url'],
                username=calendar_cfg.get('username'),
                password=calendar_cfg.get('password')
            ))
        else:
            logger.warning(f"Unknown calendar type: {calendar_cfg['type']}")
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

        for event in events:
            start = event['start']
            end = event['end']
            summary = event.get('summary', '')

            if not summary:
                logger.info(f"Skipping event: {event.get('id')} {start} - {end} due to missing summary")
                continue

            if summary.lower().strip() == 'busy':
                logger.info(f"Skipping busy event: {event.get('id')} {start} - {end}")
                continue
            
            if 'T' not in start or 'T' not in end:
                logger.info(f"Skipping all-day event: {event.get('id')} {start} - {end}")
                continue

            for target in calendars:
                if target == source:
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
                            last_synced_time=datetime.now(timezone.utc)
                        )
                        session.add(new_mapping)
                        session.commit()
                    else:
                        logger.debug(f"Busy event already exists for {event['id']} in {target.id}")

                except Exception:
                    logger.exception(f"Failed to create busy event in {target.id}")
                    failed_calendars.add(target.id)
    
    if failed_calendars:
        logger.error(f"Failed to create busy events for calendars: {', '.join(failed_calendars)}")
    else:
        logger.info("Calendar sync completed successfully.")

if __name__ == "__main__":
    main()
