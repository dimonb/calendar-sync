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
        self.calendar = self.principal.calendars()[0]  # TODO: implement calendar selection
        # Optional separate calendar (by URL) to hold the generated Busy events.
        if self.busy_calendar_id:
            self.busy_calendar = self.client.calendar(url=self.busy_calendar_id)
        else:
            self.busy_calendar = self.calendar

    def list_events(self, time_min, time_max):
        """Return a list of events in the format [{'id': str, 'start': str, 'end': str}]"""
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
                logger.debug (repr(vevent))
                results.append({
                    'id': str(vevent.uid.value),
                    'start': vevent.dtstart.value.isoformat(),
                    'end': vevent.dtend.value.isoformat(),
                    'summary': vevent.summary.value,
                    'description': str(vevent.description.value) if hasattr(vevent, 'description') else '',
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

        self.busy_calendar.add_event(busy_ics)
        return busy_id

    def _delete(self, cal, event_id):
        # Delete directly by URL. We generate the UID ourselves and the server
        # stores it at <calendar>/<uid>.ics, so we can skip cal.event(uid) which
        # otherwise REPORTs and parses the whole calendar (very slow on Yandex).
        event_url = str(cal.url).rstrip("/") + "/" + event_id + ".ics"
        try:
            cal.client.delete(event_url)
            logger.info(f"Deleted busy event {event_id}")
        except Exception:
            logger.exception(f"Failed to delete busy event {event_id}")

    def delete_event(self, event_id):
        """Delete a busy event (from the busy calendar if configured)."""
        self._delete(self.busy_calendar, event_id)

    def delete_main_event(self, event_id):
        """Delete an event from the main calendar (never the busy calendar)."""
        self._delete(self.calendar, event_id)


BaseCalendar.register(CaldavCalendar)