from calendar_sync.calendars.base import BaseCalendar

@BaseCalendar.register
class OutlookCalendar(BaseCalendar):
    type = 'outlook'

    def list_events(self, time_min, time_max):
        return []

    def create_busy_event(self, start, end, source_event_id=None):
        return "mock-outlook-event-id"