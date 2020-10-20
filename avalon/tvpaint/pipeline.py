import os
from .. import api, io
# from ..pipeline import AVALON_CONTAINER_ID

from pyblish import api as pyblish


def install():
    """Install Maya-specific functionality of avalon-core.

    This function is called automatically on calling `api.install(maya)`.

    """
    io.install()

    # Create workdir folder if does not exist yet
    workdir = api.Session["AVALON_WORKDIR"]
    if not os.path.exists(workdir):
        os.makedirs(workdir)

    pyblish.register_host("tvpaint")


def uninstall():
    """Uninstall TVPaint-specific functionality of avalon-core.

    This function is called automatically on calling `api.uninstall()`.

    """

    pyblish.deregister_host("tvpaint")


def ls():
    return []
