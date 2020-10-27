import os
import sys
import signal
import time
import traceback
import ctypes
import platform
import logging

import avalon
from avalon import style
from avalon.tvpaint import pipeline
from avalon.tvpaint.communication_server import CommunicatorWrapper
from avalon.vendor.Qt import QtWidgets, QtCore, QtGui

log = logging.getLogger(__name__)


def safe_excepthook(*args):
    traceback.print_exception(*args)


class MainThreadChecker(QtCore.QThread):
    to_execute = QtCore.Signal(object)

    def __init__(self, communicator):
        super(MainThreadChecker, self).__init__()
        self.communicator = communicator
        self.is_running = False

    def run(self):
        self.is_running = True
        while self.is_running:
            item = self.communicator.main_thread_listen()
            if item:
                self.to_execute.emit(item)
            else:
                time.sleep(0.2)


def process_in_main_thread(main_thread_item):
    log.debug("Executing process in main thread")
    if main_thread_item.done:
        log.warning("- item is processed")
        return

    callback = main_thread_item.callback
    args = main_thread_item.args
    kwargs = main_thread_item.kwargs
    log.info("Running callback: {}".format(str(callback)))
    try:
        result = callback(*args, **kwargs)
        main_thread_item.result = result

    except Exception:
        main_thread_item.exc_info = sys.exc_info()

    finally:
        main_thread_item.done = True


def avalon_icon_path():
    avalon_repo = os.path.dirname(
        os.path.dirname(os.path.abspath(avalon.__file__))
    )
    full_path = os.path.join(
        avalon_repo, "res", "icons", "png", "avalon-logo-128.png"
    )
    if os.path.exists(full_path):
        return full_path
    return None


def main(app_executable, debug=False):
    sys.excepthook = safe_excepthook

    # Create QtApplication for tools
    qt_app = QtWidgets.QApplication([])
    qt_app.setQuitOnLastWindowClosed(False)
    qt_app.setStyleSheet(style.load_stylesheet())

    if platform.system().lower() == "windows":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            u"WebsocketServer"
        )
    icon_path = avalon_icon_path()
    if icon_path:
        icon = QtGui.QIcon(icon_path)
        qt_app.setWindowIcon(icon)

    # Execute pipeline installation
    pipeline.install()

    communicator = CommunicatorWrapper.create_communicator(qt_app)
    communicator.launch(app_executable)

    main_thread_executor = MainThreadChecker(communicator)
    main_thread_executor.to_execute.connect(process_in_main_thread)
    main_thread_executor.start()

    # Register terminal signal handler
    def signal_handler(*_args):
        print("You pressed Ctrl+C. Process ended.")
        communicator.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run Qt application event processing
    sys.exit(qt_app.exec_())


if __name__ == "__main__":
    executable_path = sys.argv[0]
    main(executable_path)
