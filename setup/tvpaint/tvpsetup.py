import os

import avalon.api
import avalon.tvpaint

def main():
    # For the GUI-tools to work best, this should now become a QT-app:

    # set some environmentals to be able to do something:
    avalon.api.Session["AVALON_PROJECT"] = "dummy"
    avalon.api.Session["AVALON_TASK"] = "dummy"
    avalon.api.Session["AVALON_ASSET"] = "dummy"
    avalon.api.Session["AVALON_SILO"] = "dummy"
    if not "AVALON_ROOT" in avalon.api.Session:
        avalon.api.Session["AVALON_ROOT"] = os.path.expanduser("~")

    avalon.api.Session["AVALON_APP"] = "tvpaint"
    avalon.api.install(avalon.tvpaint)
