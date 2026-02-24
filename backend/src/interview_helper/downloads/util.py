from datetime import datetime
import ulid
from dateutil.relativedelta import relativedelta


def extract_timestamp_from_ulid(ulid_str: str) -> datetime:
    """Extract timestamp from a ULID string."""
    ulid_obj: ulid.ULID = ulid.ULID.from_str(ulid_str.upper())  # pyright: ignore[reportAny]
    timestamp_float = ulid_obj.timestamp
    return datetime.fromtimestamp(timestamp_float)


def human_readable(delta: relativedelta) -> list[str]:
    attrs = ["years", "months", "days", "hours", "minutes", "seconds"]

    return [
        "%d %s"
        % (getattr(delta, attr), attr if getattr(delta, attr) > 1 else attr[:-1])
        for attr in attrs
        if getattr(delta, attr)
    ]
