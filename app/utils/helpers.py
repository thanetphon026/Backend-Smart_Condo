import datetime
import pytz

def get_bkk_time():
    """Returns current time in Bangkok timezone."""
    tz = pytz.timezone('Asia/Bangkok')
    return datetime.datetime.now(tz)
