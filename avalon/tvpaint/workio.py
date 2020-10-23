"""Host API required for Work Files.
# TODO @iLLiCiT implement functions:
    open_file
    save_file
    current_file
    has_unsaved_changes
"""

from avalon import api
from avalon.tvpaint.communication_server import CommunicatorWrapper


def open_file(filepath):
    """Open the scene file in Blender."""
    george_script = "tv_LoadProject {}".format(filepath.replace("\\", "/"))
    result = CommunicatorWrapper.send_request(
        "execute_george", [george_script]
    )
    print(result)
    return result


def save_file(filepath):
    """Save the open scene file."""
    george_script = "tv_SaveProject {}".format(filepath.replace("\\", "/"))
    result = CommunicatorWrapper.send_request(
        "execute_george", [george_script]
    )
    print(result)
    return result


def current_file():
    """Return the path of the open scene file."""
    george_script = "tv_GetProjectName"
    result = CommunicatorWrapper.send_request(
        "execute_george", [george_script]
    )
    print(result)
    return result


def has_unsaved_changes():
    """Does the open scene file have unsaved changes?"""
    return False


def file_extensions():
    """Return the supported file extensions for Blender scene files."""
    return api.HOST_WORKFILE_EXTENSIONS["tvpaint"]


def work_root(session):
    """Return the default root to browse for work files."""
    return session["AVALON_WORKDIR"]
