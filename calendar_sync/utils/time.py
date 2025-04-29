import datetime

def get_time_window(days):
    now = datetime.datetime.now(datetime.timezone.utc)
    time_min = now.isoformat(timespec='seconds').replace('+00:00', 'Z')
    time_max = (now + datetime.timedelta(days=days)).isoformat(timespec='seconds').replace('+00:00', 'Z')
    return time_min, time_max