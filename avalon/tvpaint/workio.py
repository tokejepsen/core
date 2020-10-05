"""Host API required for Work Files."""
import socket
from pathlib import Path
import os
import pytvpaint_avalon.functions as tvp


def open_file(filepath):
    """To open a tvpaint-project we send a command to the TVPlistenerplugin
    The command sets a `tv_userstring`. Which can be read by 
    another TVPaint-function that probably is invoked by the user.
    """
    ret = tvp.open_tvproject(filepath)
    return True


def save_file(filepath):
    """Save a project to the avalonsilo.
    :filepath: the path of a local tvpaint-project
    :returns: destination-path if succeeded"""

    #path = filepath.replace("\\", "/")
    #nuke.scriptSaveAs(path)
    #nuke.Root()["name"].setValue(path)

    #nuke.Root()["project_directory"].setValue(os.path.dirname(path))
    #nuke.Root().setModified(False)
    #tvpav.save_file()
    return tvp.save_tvproject(filepath)


def current_file():
    """Return the path of the open scene file."""
    return tvp.get_currentfile()


def work_root(session):
    """Return the path of the workroot."""
    work_dir = session.get("AVALON_WORKDIR")
    scene_dir = session.get("AVALON_SCENEDIR")
    if scene_dir:
        return str(Path(work_dir, scene_dir))
    print("Workdir:", work_dir)
    return work_dir


def file_extensions():
    """Return the supported file extensions for tvpaint scene files."""
    return [".tvpp", ".tvp"]


def has_unsaved_changes():
    """Always return false so that one can allways open a tvpproject"""
    return False
