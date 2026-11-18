"""Fix Vista-style command-link text on dark MO2 themes."""

import mobase # pyright: ignore[reportMissingModuleSource]
from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtGui import QBrush, QPalette
from PyQt6.QtWidgets import QApplication, QCommandLinkButton


VISTA_PROPERTY = "_qt_usingVistaStyle"
FIXED_PROPERTY = "vistaDarkCommandLinkFixed"
ORIGINAL_BRUSH_PROPERTY = "vistaDarkCommandLinkOriginalBrush"
APPLIED_BRUSH_PROPERTY = "vistaDarkCommandLinkAppliedBrush"
STYLESHEET_PROPERTY = "vistaDarkCommandLinkStylesheet"


class CommandLinkFilter(QObject):
    def __init__(self, plugin):
        super().__init__(plugin.application)
        self.plugin = plugin

    def eventFilter(self, watched, event):
        if isinstance(watched, QCommandLinkButton) and event.type() in (
            QEvent.Type.Show,
            QEvent.Type.StyleChange,
            QEvent.Type.PaletteChange,
        ):
            self.plugin.update_button(watched)
        return False


class WindowsVistaThemeFix(mobase.IPlugin):
    def __init__(self):
        super().__init__()
        self.application = None
        self.event_filter = None

    def init(self, organizer):
        self.application = QApplication.instance()
        if self.application is None:
            print("Windows Vista Theme Fix: QApplication is not available.")
            return False

        organizer.onUserInterfaceInitialized(self.start)
        return True

    def start(self, window):
        self.event_filter = CommandLinkFilter(self)
        self.application.installEventFilter(self.event_filter)
        self.refresh_buttons()

    def update_button(self, button):
        palette = button.palette()
        active = QPalette.ColorGroup.Active
        inactive = QPalette.ColorGroup.Inactive
        text = QPalette.ColorRole.ButtonText
        background = palette.color(active, QPalette.ColorRole.Window)
        foreground = palette.brush(inactive, text)
        dark_theme = background.lightness() < 128 and foreground.color().lightness() > background.lightness()
        fixed = bool(button.property(FIXED_PROPERTY))
        stylesheet = self.application.styleSheet()

        if fixed and button.property(STYLESHEET_PROPERTY) != stylesheet:
            # A new stylesheet owns the palette now, do not restore the old one.
            button.setProperty(FIXED_PROPERTY, False)
            button.setProperty(ORIGINAL_BRUSH_PROPERTY, None)
            button.setProperty(APPLIED_BRUSH_PROPERTY, None)
            button.setProperty(STYLESHEET_PROPERTY, None)
            fixed = False

        if dark_theme and (fixed or button.property(VISTA_PROPERTY)):
            if button.property(VISTA_PROPERTY):
                button.setProperty(ORIGINAL_BRUSH_PROPERTY, palette.brush(active, text))
                button.setProperty(STYLESHEET_PROPERTY, stylesheet)
                button.setProperty(FIXED_PROPERTY, True)
                button.setProperty(VISTA_PROPERTY, False)
                fixed = True
                button.update()
            if palette.brush(active, text) != foreground:
                # Vista hard-codes a dark blue active text color and animates it.
                palette.setBrush(active, text, foreground)
                button.setProperty(APPLIED_BRUSH_PROPERTY, foreground)
                button.setPalette(palette)
        elif fixed:
            original = button.property(ORIGINAL_BRUSH_PROPERTY)
            applied = button.property(APPLIED_BRUSH_PROPERTY)
            if isinstance(original, QBrush) and isinstance(applied, QBrush):
                if palette.brush(active, text) == applied:
                    palette.setBrush(active, text, original)
                    button.setPalette(palette)
            button.setProperty(VISTA_PROPERTY, True)
            button.setProperty(FIXED_PROPERTY, False)
            button.setProperty(ORIGINAL_BRUSH_PROPERTY, None)
            button.setProperty(APPLIED_BRUSH_PROPERTY, None)
            button.setProperty(STYLESHEET_PROPERTY, None)
            button.update()

    def refresh_buttons(self):
        for window in self.application.topLevelWidgets():
            if window.isVisible():
                for button in window.findChildren(QCommandLinkButton):
                    self.update_button(button)

    def name(self):
        return "Windows Vista Theme Fix"

    def author(self):
        return "Arisinka"

    def description(self):
        return "Fixes command-link text in dark themes using the Windows Vista style."

    def version(self):
        return mobase.VersionInfo(1, 0, 0)

    def settings(self):
        return []

    def enabledByDefault(self):
        return True


def createPlugin():
    return WindowsVistaThemeFix()