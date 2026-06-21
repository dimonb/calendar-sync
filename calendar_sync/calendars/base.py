from abc import ABC, abstractmethod

import logging

logger = logging.getLogger(__name__)

class BaseCalendar(ABC):
    class_registry = {}

    @classmethod
    def register(cls, registering_class):
        cls.class_registry[registering_class.type] = registering_class
        return registering_class

    def __init__(self, cfg):
        self.onlysource = cfg.get('onlysource', False)
        # Optional separate calendar to hold the generated "Busy" events.
        # When set, busy events are created/deleted there instead of on the
        # calendar's own id (list_events still reads the real calendar).
        self.busy_calendar_id = cfg.get('busy_calendar_id')

    @abstractmethod
    def list_events(self, time_min, time_max):
        """Return a list of events in the format [{'id': str, 'start': str, 'end': str}]"""
        pass

    @abstractmethod
    def create_busy_event(self, start, end, source_event_id=None):
        """Create a Busy event. Return the ID of the created event."""
        pass

    @abstractmethod
    def delete_event(self, event_id):
        """Delete an event by its ID"""
        pass

    def delete_main_event(self, event_id):
        """Delete an event from the calendar's own id (never the busy calendar).

        Defaults to delete_event; overridden by backends that support a
        separate busy_calendar_id.
        """
        self.delete_event(event_id)

    @classmethod
    def get_calendar(cls, cfg):
        if cfg['type'] not in cls.class_registry:
            raise ValueError(f"Unknown calendar type: {cfg['type']}")
        return cls.class_registry[cfg['type']](cfg)
