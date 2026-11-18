"""Bulk-delete selected MO2 downloads.

Use the Downloads context menu to move selected ZIP, RAR, and 7Z archives and
their adjacent .meta files to the Recycle Bin after confirmation.
"""
import ctypes
import os
from ctypes import wintypes

import mobase # pyright: ignore[reportMissingModuleSource]
from mobase.widgets import TaskDialog, TaskDialogButton  # pyright: ignore[reportMissingModuleSource]

from PyQt6.QtCore import QAbstractProxyModel, QCoreApplication, QEvent, QObject, QTimer, qWarning
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeView,
)

YES = QMessageBox.StandardButton.Yes
CANCEL = QMessageBox.StandardButton.Cancel


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_ushort),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


FO_DELETE = 0x3
FOF_SILENT = 0x4
FOF_ALLOWUNDO = 0x40
FOF_NOERRORUI = 0x400
FOF_WANTNUKEWARNING = 0x4000
SUPPORTED_EXTENSIONS = {".zip", ".rar", ".7z"}


def tr(text):
    return QCoreApplication.translate("BulkDeleteDownloads", text)


def mo_tr(text):
    return QCoreApplication.translate("DownloadListView", text)


def is_inside(path, folder):
    try:
        path = os.path.normcase(os.path.realpath(path))
        folder = os.path.normcase(os.path.realpath(folder))
        return path != folder and os.path.commonpath([path, folder]) == folder
    except ValueError:
        return False


def recycle_file(path):
    operation = SHFILEOPSTRUCTW()
    operation.wFunc = FO_DELETE
    operation.pFrom = path + "\0"
    operation.fFlags = (
        FOF_ALLOWUNDO | FOF_SILENT | FOF_NOERRORUI | FOF_WANTNUKEWARNING
    )
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    return (
        result == 0
        and not operation.fAnyOperationsAborted
        and not os.path.exists(path)
    )


class DownloadsMenuFilter(QObject):
    def __init__(self, view, plugin):
        super().__init__(view)
        self.view = view
        self.plugin = plugin

    def eventFilter(self, watched, event):
        if (event.type() == QEvent.Type.Show
                and isinstance(watched, QMenu)
                and watched.parent() == self.view):
            try:
                watched.addSeparator()
                action = watched.addAction(tr("Delete Selected Downloads..."))
                action.triggered.connect(
                    lambda: QTimer.singleShot(0, self.plugin.delete_selected)
                )
            except (RuntimeError, TypeError) as error:
                qWarning(f"Bulk delete downloads: Could not add menu action: {error}")
        return False


class BulkDeleteDownloads(mobase.IPlugin):
    def __init__(self):
        super().__init__()
        self.organizer = None
        self.menu_filter = None
        self.downloads_view = None
        self.downloads_refresh = None

    def init(self, organizer):
        self.organizer = organizer
        if not organizer.onUserInterfaceInitialized(self.attach_menu):
            qWarning("Bulk delete downloads: Could not register UI initialization callback")
            return False
        return True

    def attach_menu(self, window):
        view = window.findChild(QTreeView, "downloadView")
        self.downloads_refresh = window.findChild(QPushButton, "btnRefreshDownloads")
        if view is None:
            qWarning("Bulk delete downloads: Downloads view not found")
            return
        if self.downloads_refresh is None:
            qWarning("Bulk delete downloads: Downloads refresh button not found")
        self.downloads_view = view
        view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.menu_filter = DownloadsMenuFilter(view, self)
        QApplication.instance().installEventFilter(self.menu_filter)

    def name(self):
        return "Bulk delete downloads"

    def author(self):
        return "Arisinka"

    def description(self):
        return "Select and move multiple files from the Downloads folder to the Recycle Bin."

    def version(self):
        return mobase.VersionInfo(1, 0, 0)

    def settings(self):
        return []

    def delete_selected(self):
        try:
            self.delete_selected_inner()
        except Exception as error:
            QMessageBox.critical(
                QApplication.activeWindow(),
                self.name(),
                tr("Could not process the selected downloads. "
                   "Some files may already have been moved:\n{error}").format(error=error),
            )

    def delete_selected_inner(self):
        view = self.downloads_view
        if view is None or view.model() is None or view.selectionModel() is None:
            raise RuntimeError(tr("The Downloads view is not available."))
        downloads_path = self.organizer.downloadsPath()
        if not downloads_path or not os.path.isabs(downloads_path):
            raise RuntimeError(tr("The Downloads folder path is not absolute."))
        downloads_path = os.path.abspath(downloads_path)
        if not os.path.isdir(downloads_path):
            raise RuntimeError(
                tr("The Downloads folder does not exist:\n{path}").format(path=downloads_path)
            )

        model = view.model()
        rows = sorted({index.row() for index in view.selectionModel().selectedIndexes()})
        if not rows:
            QMessageBox.information(view, self.name(), tr("Select downloads to delete."))
            return

        paths = []
        seen = set()
        errors = []
        for row in rows:
            index = model.index(row, 0)
            source_model = model
            while isinstance(source_model, QAbstractProxyModel):
                index = source_model.mapToSource(index)
                source_model = source_model.sourceModel()
            if not index.isValid():
                errors.append(tr("Row {row}: could not resolve the download.").format(row=row + 1))
                continue
            try:
                # In MO2 2.5.2, downloadPath takes the source-model row.
                path = self.organizer.downloadManager().downloadPath(index.row())
            except RuntimeError as error:
                errors.append(tr("Row {row}: could not resolve the download ({error}).").format(
                    row=row + 1, error=error
                ))
                continue
            if not path:
                errors.append(tr("Row {row}: no download path is available.").format(row=row + 1))
                continue
            if not os.path.isabs(path):
                errors.append(tr("Row {row}: the download path is not absolute.").format(
                    row=row + 1
                ))
                continue
            path = os.path.abspath(path)
            if (os.path.splitext(path)[1].lower() not in SUPPORTED_EXTENSIONS
                    or not is_inside(path, downloads_path)
                    or not os.path.isfile(path)
                    or os.path.islink(path)
                    or os.path.exists(path + ".unfinished")):
                errors.append(
                    tr("{name}: not an available, completed ZIP, RAR, or 7Z archive "
                       "in Downloads.").format(name=os.path.basename(path))
                )
                continue
            key = os.path.normcase(path)
            if key not in seen:
                seen.add(key)
                paths.append(path)

        if errors:
            QMessageBox.warning(
                view, self.name(),
                tr("No files were moved because some selected downloads are not available "
                   "for deletion:\n\n") + "\n".join(errors),
            )
            return

        preview = "\n".join(paths[:10])
        if len(paths) > 10:
            preview += "\n" + tr("... and {count} more").format(count=len(paths) - 10)
        dialog = TaskDialog(
            view,
            tr("Delete downloads"),
            tr("Are you sure you want to delete the selected downloads?"),
            preview,
            icon=QMessageBox.Icon.Question,
            buttons=[
                TaskDialogButton(mo_tr("Move to the Recycle Bin"), YES),
                TaskDialogButton(mo_tr("Cancel"), CANCEL),
            ],
        )
        answer = dialog.exec()
        if answer != YES:
            return

        failures = []
        for path in paths:
            if (not is_inside(path, downloads_path)
                    or not os.path.isfile(path)
                    or os.path.islink(path)
                    or os.path.exists(path + ".unfinished")):
                failures.append(tr("{name}: file is no longer available").format(
                    name=os.path.basename(path)
                ))
                continue

            meta_path = path + ".meta"
            if os.path.lexists(meta_path) and (
                    os.path.islink(meta_path)
                    or not os.path.isfile(meta_path)
                    or not is_inside(meta_path, downloads_path)):
                failures.append(tr("{name}: invalid metadata file").format(
                    name=os.path.basename(meta_path)
                ))
                continue

            try:
                recycled = recycle_file(path)
            except OSError as error:
                failures.append(f"{os.path.basename(path)}: {error}")
                continue
            if not recycled:
                failures.append(tr("{name}: could not move to Recycle Bin").format(
                    name=os.path.basename(path)
                ))
                continue

            if os.path.lexists(meta_path):
                if (os.path.islink(meta_path) or not os.path.isfile(meta_path)
                        or not is_inside(meta_path, downloads_path)):
                    failures.append(tr("{name}: invalid metadata file").format(
                        name=os.path.basename(meta_path)
                    ))
                    continue
                try:
                    meta_recycled = recycle_file(meta_path)
                except OSError as error:
                    failures.append(f"{os.path.basename(meta_path)}: {error}")
                    continue
                if not meta_recycled:
                    failures.append(
                        tr("{name}: could not move to Recycle Bin").format(
                            name=os.path.basename(meta_path)
                        )
                    )

        if self.downloads_refresh is not None:
            self.downloads_refresh.click()
        if failures:
            QMessageBox.warning(view, tr("Some files could not be moved"), "\n".join(failures))


def createPlugin():
    return BulkDeleteDownloads()
