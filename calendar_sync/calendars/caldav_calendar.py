from caldav import DAVClient
from icalendar import Calendar, Event
from calendar_sync.calendars.base import BaseCalendar
from dateutil import parser as date_parser
import logging
import uuid

logger = logging.getLogger(__name__)

class CaldavCalendar(BaseCalendar):
    type = 'caldav'

    def __init__(self, cfg):
        super().__init__(cfg)
        self.url = cfg['url']
        self.username = cfg['username']
        self.password = cfg['password']
        self.id = f"caldav-{self.url}"
        self.client = DAVClient(
            self.url,
            username=self.username,
            password=self.password
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
                logger.debug (vevent)
                results.append({
                    'id': str(vevent.uid.value),
                    'start': vevent.dtstart.value.isoformat(),
                    'end': vevent.dtend.value.isoformat(),
                    'summary': vevent.summary.value,
                    'object': event 
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

    def delete_event(self, event_id):
        """Удалить событие по его ID"""
        try:
            event = self.calendar.event(event_id)
            event.delete()
            logger.info(f"Deleted busy event {event_id}")
        except Exception:
            logger.exception(f"Failed to delete busy event {event_id}")


BaseCalendar.register(CaldavCalendar)