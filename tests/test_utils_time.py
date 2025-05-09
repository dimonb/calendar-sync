import re
from calendar_sync.utils import time as time_utils

def test_get_time_window_format():
    time_min, time_max = time_utils.get_time_window(5)
    # They should both end with Z and contain 'T'.
    assert time_min.endswith('Z')
    assert time_max.endswith('Z')
    assert 'T' in time_min
    assert 'T' in time_max
    # Check ISO format YYYY-MM-DDTHH:MM:SSZ
    r = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
    assert re.match(r, time_min)
    assert re.match(r, time_max)
    # They must be different (window is not zero)
    assert time_min != time_max
    # Check order
    assert time_min < time_max
