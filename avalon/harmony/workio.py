"""Host API required Work Files tool"""
import os
import shutil

from . import lib
from avalon import api


def file_extensions():
    return api.HOST_WORKFILE_EXTENSIONS["harmony"]


def has_unsaved_changes():
    if lib.server:
        return lib.server.send({"function": "scene.isDirty"})["result"]

    return False


def save_file(filepath):
    temp_path = lib.get_local_harmony_path(filepath)

    if os.path.exists(temp_path):
        shutil.rmtree(temp_path)

    lib.server.send(
        {"function": "scene.saveAs", "args": [temp_path]}
    )["result"]

    lib.zip_and_move(temp_path, filepath)

    lib.workfile_path = filepath

    func = """function add_path(path)
    {
        var app = QCoreApplication.instance();
        app.watcher.addPath(path);
    }
    add_path
    """

    scene_path = os.path.join(
        temp_path, os.path.basename(temp_path) + ".xstage"
    )
    lib.server.send(
        {"function": func, "args": [scene_path]}
    )


def open_file(filepath):
    lib.launch_zip_file(filepath)


def current_file():
    """Returning None to make Workfiles app look at first file extension."""
    return None


def work_root(session):
    return os.path.normpath(session["AVALON_WORKDIR"]).replace("\\", "/")
