from sqlalchemy import Column, String, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class EventMapping(Base):
    __tablename__ = 'event_mappings'

    source_calendar = Column(String, primary_key=True)
    source_event_id = Column(String, primary_key=True)
    target_calendar = Column(String, primary_key=True)
    busy_event_id = Column(String, nullable=False)
    last_synced_time = Column(DateTime)