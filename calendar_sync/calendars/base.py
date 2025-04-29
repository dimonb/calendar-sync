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

    @abstractmethod
    def list_events(self, time_min, time_max):
        """Вернуть список событий в формате [{'id': str, 'start': str, 'end': str}]"""
        pass

    @abstractmethod
    def create_busy_event(self, start, end, source_event_id=None):
        """Создать событие типа Busy. Вернуть ID созданного события."""
        pass

    @abstractmethod
    def delete_event(self, event_id):
        """Удалить событие по его ID"""
        pass

    @classmethod
    def get_calendar(cls, cfg):
        if cfg['type'] not in cls.class_registry:
            raise ValueError(f"Unknown calendar type: {cfg['type']}")
        return cls.class_registry[cfg['type']](cfg)
