import sys
import signal
import time
import traceback

from . import pipeline, communication_server
from avalon.vendor.Qt import QtWidgets, QtCore

from pype.api import Logger

log = Logger().get_logger(__name__)


def safe_excepthook(*args):
    traceback.print_exception(*args)


class MainWindow(QtWidgets.QMainWindow):
    """Window to keep QtApplication run."""
    def __init__(self, app):
        super(MainWindow, self).__init__()
        self.app = app


class ProcessAliveChecker(QtCore.QThread):
    def __init__(self, communicator, qt_app):
        super(ProcessAliveChecker, self).__init__()
        self.process = communicator.process
        self.websocket_server = communicator.websocket_server
        self.qt_app = qt_app

    def run(self):
        self.process.wait()
        self.websocket_server.stop()
        self.qt_app.quit()


class MainThreadChecker(QtCore.QThread):
    to_execute = QtCore.Signal(object)

    def __init__(self, communicator):
        super(MainThreadChecker, self).__init__()
        self.communicator = communicator
        self.is_running = False

    def run(self):
        self.is_running = True
        while self.is_running:
            callback = self.communicator.main_thread_listen()
            if callback:
                self.to_execute.emit(callback)
            else:
                time.sleep(0.2)


def process_in_main_thread(callback):
    log.info("Running callback: {}".format(str(callback)))
    callback()


def main(app_executable):
    sys.excepthook = safe_excepthook

    # Create QtApplication for tools
    qt_app = QtWidgets.QApplication([])
    qt_app.setQuitOnLastWindowClosed(False)

    # Create any Qt window to keep QtApplicaiton alive if none of other
    # tools are shown
    # _main_window = MainWindow(qt_app)

    # Execute pipeline installation
    pipeline.install()

    communicator = communication_server.Communicator(qt_app)
    communicator.launch(app_executable)

    main_thread_executor = MainThreadChecker(communicator)
    main_thread_executor.to_execute.connect(process_in_main_thread)

    porcess_alive_checker = ProcessAliveChecker(communicator, qt_app)

    porcess_alive_checker.start()
    main_thread_executor.start()

    # Register terminal signal handler
    def signal_handler(*args):
        print("You pressed Ctrl+C. Process ended.")
        communicator.stop()
        qt_app.quit()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run Qt application event processing
    sys.exit(qt_app.exec_())


if __name__ == "__main__":
    main()
