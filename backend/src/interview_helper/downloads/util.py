from datetime import datetime, timezone
import ulid
from dateutil.relativedelta import relativedelta


def extract_timestamp_from_ulid(ulid_str: str) -> datetime:
    """Extract timestamp from a ULID string as a UTC datetime."""
    ulid_obj: ulid.ULID = ulid.ULID.from_str(ulid_str.upper())  # pyright: ignore[reportAny]
    timestamp_float = ulid_obj.timestamp
    return datetime.fromtimestamp(timestamp_float, tz=timezone.utc)


def human_readable(delta: relativedelta) -> list[str]:
    attrs = ["years", "months", "days", "hours", "minutes", "seconds"]

    return [
        "%d %s"
        % (getattr(delta, attr), attr if getattr(delta, attr) > 1 else attr[:-1])
        for attr in attrs
        if getattr(delta, attr)
    ]


def sanitize_filename(name: str, default: str = "download") -> str:
    """
    Sanitize a string to create a safe filename.

    - Strips control characters (CR, LF, etc.)
    - Allows only alphanumeric characters, underscores, hyphens, and dots
    - Limits length to 200 characters
    - Returns default if result is empty

    Args:
        name: The string to sanitize
        default: Default filename if sanitization results in empty string

    Returns:
        A safe filename string
    """
    import re

    # Remove control characters (ASCII 0-31 and 127)
    name = "".join(char for char in name if ord(char) >= 32 and ord(char) != 127)

    # Replace spaces with underscores
    name = name.replace(" ", "_")

    # Keep only alphanumeric, underscore, hyphen, and dot
    name = re.sub(r"[^a-zA-Z0-9._-]", "", name)

    # Limit length
    name = name[:200]

    # Strip leading/trailing dots and underscores to avoid hidden files or weird names
    name = name.strip("._")

    # Return default if empty
    return name if name else default
