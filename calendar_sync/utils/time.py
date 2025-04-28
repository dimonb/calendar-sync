import datetime

def get_time_window(weeks=3):
    """Возвращает (time_min, time_max) для запроса событий."""
    now = datetime.datetime.utcnow()
    time_min = now.isoformat() + 'Z'
    time_max = (now + datetime.timedelta(weeks=weeks)).isoformat() + 'Z'
    return time_min, time_max