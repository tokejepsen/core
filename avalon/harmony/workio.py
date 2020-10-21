"""Host API required Work Files tool"""
import os
import shutil

from . import lib
from avalon import api

# used to lock saving until previous save is done.
save_disabled = False


def file_extensions():
    return api.HOST_WORKFILE_EXTENSIONS["harmony"]


def has_unsaved_changes():
    if lib.server:
        return lib.server.send({"function": "scene.isDirty"})["result"]

    return False


def save_file(filepath):
    global save_disabled
    if save_disabled:
        return lib.server.send(
            {
                "function": "show_message",
                "args": "Saving in progress, please wait until it finishes."
            })["result"]

    save_disabled = True
    temp_path = lib.get_local_harmony_path(filepath)

    if os.path.exists(temp_path):
        shutil.rmtree(temp_path)

    lib.server.send(
        {"function": "scene.saveAs", "args": [temp_path]}
    )["result"]

    lib.zip_and_move(temp_path, filepath)

    lib.workfile_path = filepath
    sig = lib.signature("add_path")
    func = """function %s(path)
    {
        var app = QCoreApplication.instance();
        app.watcher.addPath(path);
    }
    %s
    """ % (sig, sig)

    scene_path = os.path.join(
        temp_path, os.path.basename(temp_path) + ".xstage"
    )
    lib.server.send(
        {"function": func, "args": [scene_path]}
    )
    save_disabled = False


def open_file(filepath):
    lib.launch_zip_file(filepath)


def current_file():
    """Returning None to make Workfiles app look at first file extension."""
    return None


def work_root(session):
    return os.path.normpath(session["AVALON_WORKDIR"]).replace("\\", "/")
