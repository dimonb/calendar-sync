from caldav import DAVClient
from calendar_sync.calendars.base import BaseCalendar
from dateutil import parser as date_parser
import logging
import uuid

logger = logging.getLogger(__name__)

class CaldavCalendar(BaseCalendar):
    def __init__(self, url, username=None, password=None):
        super().__init__(calendar_id=f"caldav-{url}")
        self.url = url
        self.username = username
        self.password = password
        self.client = DAVClient(
            url,
            username=username,
            password=password
        )
        self.principal = self.client.principal()
        self.calendar = self.principal.calendars()[0]  # TODO: сделать выбор календаря

    def list_events(self, time_min, time_max):
        """Вернуть список событий в формате [{'id': str, 'start': str, 'end': str}]"""
        results = []

        start_dt = date_parser.isoparse(time_min)
        end_dt = date_parser.isoparse(time_max)

        events = self.calendar.search(
            start=start_dt,
            end=end_dt,
            expand=True,
            event=True
        )

        for event in events:
            try:
                vevent = event.vobject_instance.vevent
                results.append({
                    'id': event.url,
                    'start': vevent.dtstart.value.isoformat(),
                    'end': vevent.dtend.value.isoformat(),
                })
            except Exception:
                logger.exception("Failed to parse event")

        return results

    def create_busy_event(self, start, end, source_event_id=None):
        """Создать событие типа Busy"""
        busy_id = str(uuid.uuid4())
        busy_ics = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//calendar-sync//EN
BEGIN:VEVENT
UID:{busy_id}
DTSTAMP:{start.replace('-', '').replace(':', '').replace('Z', '')}
DTSTART:{start.replace('-', '').replace(':', '').replace('Z', '')}
DTEND:{end.replace('-', '').replace(':', '').replace('Z', '')}
SUMMARY:Busy
DESCRIPTION:Managed-by: calendar-sync (source {source_event_id})
STATUS:CONFIRMED
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
"""
        self.calendar.add_event(busy_ics)
        return busy_id