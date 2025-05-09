import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from calendar_sync.db.models import Base, EventMapping
import datetime

@pytest.fixture(scope="function")
def in_memory_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()

def test_event_mapping_can_be_created_and_queried(in_memory_session):
    """Test that EventMapping can be created and queried."""
    session = in_memory_session
    now = datetime.datetime.now(datetime.UTC)
    
    mapping = EventMapping(
        source_calendar="A",
        source_event_id="aaa",
        target_calendar="B",
        busy_event_id="bbb",
        start_time=now.isoformat(),
        end_time=now.isoformat(),
    )
    session.add(mapping)
    session.commit()

    # Query the mapping
    result = session.query(EventMapping).filter_by(
        source_calendar="A",
        source_event_id="aaa"
    ).first()
    assert result is not None
    assert result.target_calendar == "B"
    assert result.busy_event_id == "bbb"

    # Cleanup
    session.delete(mapping)
    session.commit()
    session.close()

def test_event_mapping_primary_key(in_memory_session):
    """Test that EventMapping primary key works correctly."""
    session = in_memory_session
    now = datetime.datetime.now(datetime.UTC)
    
    # Create first mapping
    mapping1 = EventMapping(
        source_calendar="A",
        source_event_id="aaa",
        target_calendar="B",
        busy_event_id="bbb",
        start_time=now.isoformat(),
        end_time=now.isoformat(),
    )
    session.add(mapping1)
    session.commit()

    # Try to create second mapping with same primary key
    mapping2 = EventMapping(
        source_calendar="A",
        source_event_id="aaa",
        target_calendar="C",
        busy_event_id="ccc",
        start_time=now.isoformat(),
        end_time=now.isoformat(),
    )
    session.add(mapping2)
    try:
        session.commit()
        assert False, "Should have raised an integrity error"
    except Exception:
        session.rollback()

    # Cleanup
    session.delete(mapping1)
    session.commit()
    session.close()

def test_can_update_and_delete_event_mapping(in_memory_session):
    """Test that EventMapping can be updated and deleted."""
    session = in_memory_session
    now = datetime.datetime.now(datetime.UTC)
    
    # Create mapping
    mapping = EventMapping(
        source_calendar="A",
        source_event_id="aaa",
        target_calendar="B",
        busy_event_id="bbb",
        start_time=now.isoformat(),
        end_time=now.isoformat(),
    )
    session.add(mapping)
    session.commit()

    # Update mapping
    mapping.busy_event_id = "ccc"
    session.commit()

    # Verify update
    result = session.query(EventMapping).filter_by(
        source_calendar="A",
        source_event_id="aaa"
    ).first()
    assert result is not None
    assert result.busy_event_id == "ccc"

    # Delete mapping
    session.delete(mapping)
    session.commit()

    # Verify deletion
    result = session.query(EventMapping).filter_by(
        source_calendar="A",
        source_event_id="aaa"
    ).first()
    assert result is None

    session.close()

