"""Host API required for Work Files.
# TODO @iLLiCiT implement functions:
    open_file
    save_file
    current_file
    has_unsaved_changes
"""

from avalon import api


def open_file(filepath):
    """Open the scene file in Blender."""
    return None


def save_file(filepath, copy):
    """Save the open scene file."""
    return None


def current_file():
    """Return the path of the open scene file."""
    return None


def has_unsaved_changes():
    """Does the open scene file have unsaved changes?"""
    return False


def file_extensions():
    """Return the supported file extensions for Blender scene files."""
    return api.HOST_WORKFILE_EXTENSIONS["tvpaint"]


def work_root(session):
    """Return the default root to browse for work files."""
    return session["AVALON_WORKDIR"]
