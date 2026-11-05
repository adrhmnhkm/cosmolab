"""Shared utility functions used across cosmolab modules."""


def fire_cb(cb, event_type: str, msg: str, data: dict = None):
    """Invoke a progress callback safely, supporting both (type, msg, data) and () signatures."""
    if not cb:
        return
    try:
        cb(event_type, msg, data or {})
    except TypeError:
        try:
            cb()
        except Exception:
            pass
