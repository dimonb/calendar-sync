from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from calendar_sync.db.models import Base
import os

def get_engine():
    db_path = os.getenv('DB_PATH', '/data/calendar_sync.db')
    engine = create_engine(f'sqlite:///{db_path}', echo=False, future=True)
    return engine

def get_session():
    engine = get_engine()
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return Session()