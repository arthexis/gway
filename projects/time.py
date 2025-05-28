import time as _time
import datetime

def now(*, utc=False) -> "datetime":
    """Return the current datetime object."""
    return datetime.datetime.now(datetime.timezone.utc) if utc else datetime.datetime.now()

def now_plus(*, seconds=0, utc=False) -> "datetime":
    """Return current datetime plus given seconds."""
    base = now(utc=utc)
    return base + datetime.timedelta(seconds=seconds)

def time(*, utc=False) -> str:
    """Return the current time of day as HH:MM:SS."""
    struct_time = _time.gmtime() if utc else _time.localtime()
    return _time.strftime('%H:%M:%S', struct_time)

def timestamp(*, utc=False) -> str:
    """Return the current timestamp in ISO-8601 format."""
    return now(utc=utc).isoformat().replace("+00:00", "Z" if utc else "")
