"""Host API required Work Files tool"""
import os

from . import lib
from avalon import api


def _active_document():
    if len(lib.app().Documents) < 1:
        return None

    return lib.app().ActiveDocument


def file_extensions():
    return api.HOST_WORKFILE_EXTENSIONS["photoshop"]


def has_unsaved_changes():
    if _active_document():
        return not _active_document().Saved

    return False


def save_file(filepath):
    _active_document().SaveAs(filepath)


def open_file(filepath):
    lib.app().Open(filepath)

    return True


def current_file():
    try:
        return os.path.normpath(_active_document().FullName).replace("\\", "/")
    except Exception:
        return None


def work_root(session):
    return os.path.normpath(session["AVALON_WORKDIR"]).replace("\\", "/")
