from caldav import DAVClient
import logging
import uuid

logger = logging.getLogger(__name__)

class CaldavCalendar:
    def __init__(self, url):
        self.url = url
        self.client = DAVClient(url)
        self.principal = self.client.principal()
        self.calendar = self.principal.calendars()[0]  # TODO: сделать выбор нужного календаря

        self.id = f"caldav-{self.url}"

    def list_events(self, time_min, time_max):
        """Вернуть список событий в формате [{'id': str, 'start': str, 'end': str}]"""
        results = []
        events = self.calendar.date_search(
            start=time_min,
            end=time_max,
            expand=True
        )

        for event in events:
            try:
                vevent = event.vobject_instance.vevent
                results.append({
                    'id': event.url,  # URL события как уникальный ID
                    'start': vevent.dtstart.value.isoformat(),
                    'end': vevent.dtend.value.isoformat(),
                })
            except Exception as e:
                logger.error(f"Failed to parse event: {e}")

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