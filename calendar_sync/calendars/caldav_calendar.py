from caldav import DAVClient
from icalendar import Calendar, Event
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
                    'id': str(event.url),
                    'start': vevent.dtstart.value.isoformat(),
                    'end': vevent.dtend.value.isoformat(),
                    'summary': vevent.summary.value,
                })
            except Exception:
                logger.exception("Failed to parse event")

        return results

    def create_busy_event(self, start, end, source_event_id=None):
        busy_id = str(uuid.uuid4())

        cal = Calendar()
        cal.add('prodid', '-//calendar-sync//EN')
        cal.add('version', '2.0')

        event = Event()
        event.add('uid', busy_id)
        event.add('dtstamp', date_parser.isoparse(start))
        event.add('dtstart', date_parser.isoparse(start))
        event.add('dtend', date_parser.isoparse(end))
        event.add('summary', 'Busy')
        event.add('description', f'Managed-by: calendar-sync (source {source_event_id})')
        event.add('status', 'CONFIRMED')
        event.add('transp', 'OPAQUE')

        cal.add_component(event)

        busy_ics = cal.to_ical()

        self.calendar.add_event(busy_ics)
        return busy_id