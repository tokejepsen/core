"""Helper functions"""

import datetime
from pytvpaint_avalon import functions as tvp


__all__ = [
    "time",
]


def time():
    """Return file-system safe string of current date and time"""
    return datetime.datetime.now().strftime("%Y%m%dT%H%M%SZ")


def get_instances():
    tvp.get_current_layers()
