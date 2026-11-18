"""Match Windows 11 title bar colors to each window's Qt palette."""

import ctypes
import sys
from ctypes import wintypes

import mobase # pyright: ignore[reportMissingModuleSource]
from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication, QWidget


CAPTION_COLOR = 35 # DWMWA_CAPTION_COLOR
TEXT_COLOR = 36 # DWMWA_TEXT_COLOR
DEFAULT_COLOR = 0xFFFFFFFF # The color will reset the window back to using the system's default behavior.
CAPTION_MARKER = "windows11TitleBarCaptionColor"
TEXT_MARKER = "windows11TitleBarTextColor"


def colorref(rgb):
    return ((rgb & 0xFF) << 16) | (rgb & 0x00FF00) | ((rgb >> 16) & 0xFF)


class TitleBarEventFilter(QObject):
    def __init__(self, plugin):
        super().__init__(plugin.application)
        self.plugin = plugin

    def eventFilter(self, watched, event):
        if (
            isinstance(watched, QWidget)
            and watched.isWindow()
            and event.type()
            in (
                QEvent.Type.Show,
                QEvent.Type.StyleChange,
                QEvent.Type.PaletteChange,
            )
        ):
            self.plugin.update_window(watched)
        return False


class Windows11TitleBar(mobase.IPlugin):
    def __init__(self):
        super().__init__()
        self.application = None
        self.set_attribute = None
        self.reported_errors = set()
        self.event_filter = None

    def init(self, organizer):
        if sys.platform != "win32":
            print("Windows 11 Title Bar requires Windows 11.")
            return False

        windows_version = sys.getwindowsversion()
        if windows_version.platform_version[2] < 22000:
            print(
                "Windows 11 Title Bar requires Windows 11; "
                f"reported build: {windows_version.build}, "
                f"system DLL build: {windows_version.platform_version[2]}."
            )
            return False

        self.application = QApplication.instance()
        if self.application is None:
            print("Windows 11 Title Bar: QApplication is not available.")
            return False

        self.set_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
        self.set_attribute.argtypes = (
            wintypes.HWND,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
        )
        self.set_attribute.restype = ctypes.c_long
        organizer.onUserInterfaceInitialized(self.start)
        return True

    def start(self, window):
        self.event_filter = TitleBarEventFilter(self)
        self.application.installEventFilter(self.event_filter)
        self.refresh_windows()

    def set_color(self, window, attribute, color):
        value = wintypes.DWORD(color)
        result = self.set_attribute(
            wintypes.HWND(int(window.winId())),
            attribute,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
        if result < 0:
            error = (attribute, result)
            if error not in self.reported_errors:
                self.reported_errors.add(error)
                print(
                    "Windows 11 Title Bar: DwmSetWindowAttribute failed "
                    f"for attribute {attribute}: 0x{result & 0xFFFFFFFF:08X}"
                )
            return False
        return True

    def palette_color(self, window, role):
        color = window.palette().color(QPalette.ColorGroup.Active, role)
        if not color.isValid() or color.alpha() == 0:
            return DEFAULT_COLOR
        return colorref(color.rgb())

    def update_window(self, window):
        if not window.isVisible() or window.windowType() not in (
            Qt.WindowType.Window,
            Qt.WindowType.Dialog,
            Qt.WindowType.Tool,
        ):
            return

        colors = (
            (CAPTION_COLOR, CAPTION_MARKER, QPalette.ColorRole.Window),
            (TEXT_COLOR, TEXT_MARKER, QPalette.ColorRole.WindowText),
        )
        for attribute, marker, role in colors:
            color = self.palette_color(window, role)
            if window.property(marker) != color and self.set_color(window, attribute, color):
                window.setProperty(marker, color)

    def refresh_windows(self):
        for window in self.application.topLevelWidgets():
            self.update_window(window)

    def name(self):
        return "Windows 11 Title Bar"

    def author(self):
        return "Arisinka"

    def description(self):
        return "Matches Windows 11 title bars to each window's Qt palette."

    def version(self):
        return mobase.VersionInfo(1, 0, 0)

    def settings(self):
        return []

    def enabledByDefault(self):
        return True


def createPlugin():
    return Windows11TitleBar()
