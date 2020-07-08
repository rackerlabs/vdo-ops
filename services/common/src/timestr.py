from datetime import datetime


def from_ms_timestamp(timestamp_in_ms):
    """Formats the provided timestamp in milliseconds into a string format."""
    timestr = datetime.isoformat(
        datetime.utcfromtimestamp(timestamp_in_ms // 1000).replace(
            microsecond=timestamp_in_ms % 1000 * 1000
        )
    )
    return timestr + "Z"
