from abc import ABC, abstractmethod

class BaseCalendar(ABC):
    def __init__(self, calendar_id):
        self.id = calendar_id

    @abstractmethod
    def list_events(self, time_min, time_max):
        """Вернуть список событий в формате [{'id': str, 'start': str, 'end': str}]"""
        pass

    @abstractmethod
    def create_busy_event(self, start, end, source_event_id=None):
        """Создать событие типа Busy. Вернуть ID созданного события."""
        pass