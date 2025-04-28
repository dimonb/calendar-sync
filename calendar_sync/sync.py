import os
import yaml
import logging
import datetime
from calendar_sync.db.session import get_session
from calendar_sync.db.models import EventMapping
from calendar_sync.calendars.google_calendar import GoogleCalendar
from calendar_sync.calendars.outlook_calendar import OutlookCalendar
from calendar_sync.calendars.caldav_calendar import CaldavCalendar
from calendar_sync.utils.time import get_time_window
from calendar_sync.utils.env import load_env

# Настройка логов
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

load_env()

def load_config():
    config_path = os.getenv('CONFIG_PATH', '/app/config.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def load_calendars(config):
    calendars = []
    for calendar_cfg in config.get('calendars', []):
        if calendar_cfg['type'] == 'google':
            calendars.append(GoogleCalendar(calendar_cfg['id']))
        elif calendar_cfg['type'] == 'outlook':
            calendars.append(OutlookCalendar(calendar_cfg['id']))
        elif calendar_cfg['type'] == 'caldav':
            calendars.append(CaldavCalendar(calendar_cfg['url']))
        else:
            logger.warning(f"Unknown calendar type: {calendar_cfg['type']}")
    return calendars

def main():
    logger.info("Starting calendar sync service...")
    config = load_config()
    session = get_session()

    calendars = load_calendars(config)

    if not calendars:
        logger.error("No calendars configured. Exiting.")
        return

    time_min, time_max = get_time_window(weeks=config.get('sync_window_days', 3))

    for source in calendars:
        try:
            events = source.list_events(time_min, time_max)
        except Exception as e:
            logger.error(f"Failed to fetch events from {source}: {e}")
            continue

        for event in events:
            start = event['start']
            end = event['end']

            for target in calendars:
                if target == source:
                    continue

                try:
                    mapping = session.query(EventMapping).filter_by(
                        source_calendar=source.id,
                        source_event_id=event['id'],
                        target_calendar=target.id
                    ).first()

                    if not mapping:
                        busy_event_id = target.create_busy_event(start, end, source_event_id=event['id'])
                        new_mapping = EventMapping(
                            source_calendar=source.id,
                            source_event_id=event['id'],
                            target_calendar=target.id,
                            busy_event_id=busy_event_id,
                            last_synced_time=datetime.datetime.utcnow()
                        )
                        session.add(new_mapping)

                except Exception as e:
                    logger.error(f"Failed to create busy event in {target}: {e}")

    session.commit()
    logger.info("Calendar sync completed successfully.")

if __name__ == "__main__":
    main()