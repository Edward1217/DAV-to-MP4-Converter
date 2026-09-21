import sys
import os
import time
from pathlib import Path

from PySide6.QtCore import (
    QObject,
    QThread,
    Signal,
    Qt
)

from PySide6.QtGui import (
    QDragEnterEvent,
    QDropEvent
)

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QProgressBar,
    QMessageBox,
    QHeaderView,
    QCheckBox,
    QAbstractItemView,
    QGroupBox
)

from converter import (
    dav_to_mp4,
    detect_codec
)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def format_file_size(size_bytes):

    if size_bytes < 1024:
        return f"{size_bytes} B"

    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"

    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.1f} MB"

    else:
        return f"{size_bytes / (1024 ** 3):.2f} GB"


def format_time(seconds):

    if seconds < 60:
        return f"{seconds:.1f} sec"

    minutes = int(seconds // 60)
    seconds = int(seconds % 60)

    return f"{minutes}m {seconds}s"


def codec_display_name(codec):

    if codec == "h264":
        return "H.264"

    elif codec == "hevc":
        return "H.265"

    return "Unknown"


# ============================================================
# CONVERSION WORKER
# ============================================================

class ConversionWorker(QObject):

    file_started = Signal(
        int,
        str
    )

    file_finished = Signal(
        int,
        str,
        float,
        str
    )

    overall_finished = Signal(
        int,
        int,
        int,
        float,
        bool
    )

    def __init__(
        self,
        files,
        output_folder,
        skip_existing=True
    ):

        super().__init__()

        self.files = list(files)

        self.output_folder = Path(
            output_folder
        )

        self.skip_existing = skip_existing

        self.cancelled = False


    def cancel(self):

        self.cancelled = True


    def run(self):

        success = 0
        failed = 0
        skipped = 0

        overall_start = time.time()

        self.output_folder.mkdir(
            parents=True,
            exist_ok=True
        )

        for index, dav_file in enumerate(
            self.files
        ):

            if self.cancelled:
                break

            dav_file = Path(
                dav_file
            )

            output_file = (
                self.output_folder
                /
                f"{dav_file.stem}.mp4"
            )

            # =================================================
            # SKIP EXISTING
            # =================================================

            if (
                self.skip_existing
                and
                output_file.exists()
            ):

                skipped += 1

                self.file_finished.emit(
                    index,
                    "Already exists",
                    0.0,
                    ""
                )

                continue

            # =================================================
            # START
            # =================================================

            self.file_started.emit(
                index,
                dav_file.name
            )

            file_start = time.time()

            # =================================================
            # CONVERT
            # =================================================

            try:

                dav_to_mp4(
                    dav_file,
                    output_file,
                    fps=30
                )

                elapsed = (
                    time.time()
                    -
                    file_start
                )

                success += 1

                self.file_finished.emit(
                    index,
                    "Completed",
                    elapsed,
                    ""
                )

            except Exception as error:

                elapsed = (
                    time.time()
                    -
                    file_start
                )

                failed += 1

                self.file_finished.emit(
                    index,
                    "Failed",
                    elapsed,
                    str(error)
                )

        overall_elapsed = (
            time.time()
            -
            overall_start
        )

        self.overall_finished.emit(
            success,
            failed,
            skipped,
            overall_elapsed,
            self.cancelled
        )


# ============================================================
# MAIN WINDOW
# ============================================================

class MainWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.setWindowTitle(
            "DAV to MP4 Converter V5"
        )

        self.resize(
            1100,
            700
        )

        # Enable drag & drop
        self.setAcceptDrops(
            True
        )

        # ====================================================
        # DATA
        # ====================================================

        self.dav_files = []

        # Store codec detection results
        #
        # Example:
        #
        # {
        #     Path("camera01.dav"): "h264",
        #     Path("camera02.dav"): "hevc"
        # }
        #
        self.codec_cache = {}

        # Conversion thread
        self.conversion_thread = None
        self.conversion_worker = None

        # Statistics
        self.success_count = 0
        self.failed_count = 0
        self.skipped_count = 0

        self.setup_ui()


    # ========================================================
    # UI
    # ========================================================

    def setup_ui(self):

        central = QWidget()

        self.setCentralWidget(
            central
        )

        main_layout = QVBoxLayout(
            central
        )

        # ====================================================
        # TITLE
        # ====================================================

        title = QLabel(
            "DAV to MP4 Converter"
        )

        title.setStyleSheet(
            """
            font-size: 27px;
            font-weight: bold;
            padding-top: 5px;
            """
        )

        subtitle = QLabel(
            "H.264 / H.264+ / H.265 / H.265+"
        )

        subtitle.setStyleSheet(
            """
            color: #777777;
            font-size: 13px;
            padding-bottom: 8px;
            """
        )

        main_layout.addWidget(
            title
        )

        main_layout.addWidget(
            subtitle
        )

        # ====================================================
        # OUTPUT FOLDER
        # ====================================================

        output_group = QGroupBox(
            "Output Folder"
        )

        output_layout = QHBoxLayout(
            output_group
        )

        self.output_edit = QLineEdit()

        self.output_edit.setPlaceholderText(
            "Select where MP4 files will be saved..."
        )

        self.output_browse_button = QPushButton(
            "Browse..."
        )

        self.open_output_button = QPushButton(
            "Open Folder"
        )

        self.output_browse_button.clicked.connect(
            self.select_output_folder
        )

        self.open_output_button.clicked.connect(
            self.open_output_folder
        )

        output_layout.addWidget(
            self.output_edit
        )

        output_layout.addWidget(
            self.output_browse_button
        )

        output_layout.addWidget(
            self.open_output_button
        )

        main_layout.addWidget(
            output_group
        )

        # ====================================================
        # FILE CONTROL BUTTONS
        # ====================================================

        controls = QHBoxLayout()

        self.add_files_button = QPushButton(
            "Add Files"
        )

        self.add_folder_button = QPushButton(
            "Add Folder"
        )

        self.remove_button = QPushButton(
            "Remove Selected"
        )

        self.clear_button = QPushButton(
            "Clear"
        )

        self.add_files_button.clicked.connect(
            self.add_files
        )

        self.add_folder_button.clicked.connect(
            self.add_folder
        )

        self.remove_button.clicked.connect(
            self.remove_selected
        )

        self.clear_button.clicked.connect(
            self.clear_files
        )

        controls.addWidget(
            self.add_files_button
        )

        controls.addWidget(
            self.add_folder_button
        )

        controls.addWidget(
            self.remove_button
        )

        controls.addWidget(
            self.clear_button
        )

        controls.addStretch()

        # ====================================================
        # SKIP EXISTING
        # ====================================================

        self.skip_checkbox = QCheckBox(
            "Skip existing MP4"
        )

        self.skip_checkbox.setChecked(
            True
        )

        controls.addWidget(
            self.skip_checkbox
        )

        main_layout.addLayout(
            controls
        )

        # ====================================================
        # DRAG & DROP AREA
        # ====================================================

        self.drop_label = QLabel(
            "Drag && Drop DAV Files or Folders Here"
        )

        self.drop_label.setAlignment(
            Qt.AlignCenter
        )

        self.drop_label.setMinimumHeight(
            65
        )

        self.drop_label.setStyleSheet(
            """
            QLabel {
                border: 2px dashed #999999;
                border-radius: 8px;
                color: #777777;
                font-size: 14px;
            }
            """
        )

        main_layout.addWidget(
            self.drop_label
        )

        # ====================================================
        # FILE COUNT
        # ====================================================

        self.file_count_label = QLabel(
            "0 DAV files"
        )

        main_layout.addWidget(
            self.file_count_label
        )

        # ====================================================
        # TABLE
        # ====================================================

        self.table = QTableWidget()

        self.table.setColumnCount(
            5
        )

        self.table.setHorizontalHeaderLabels([
            "DAV File",
            "Codec",
            "Size",
            "Status",
            "Time"
        ])

        # Select entire rows
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )

        # Allow selecting multiple rows
        self.table.setSelectionMode(
            QAbstractItemView.ExtendedSelection
        )

        # Prevent editing cells
        self.table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )

        # Alternating row colors
        self.table.setAlternatingRowColors(
            True
        )

        # ====================================================
        # MANUAL COLUMN RESIZE
        # ====================================================

        header = (
            self.table.horizontalHeader()
        )

        # User can manually drag column boundaries
        header.setSectionResizeMode(
            QHeaderView.Interactive
        )

        # Initial column sizes
        self.table.setColumnWidth(
            0,
            600
        )

        self.table.setColumnWidth(
            1,
            100
        )

        self.table.setColumnWidth(
            2,
            100
        )

        self.table.setColumnWidth(
            3,
            130
        )

        self.table.setColumnWidth(
            4,
            100
        )

        # Double-click converted file to open MP4
        self.table.cellDoubleClicked.connect(
            self.table_double_click
        )

        main_layout.addWidget(
            self.table
        )

        # ====================================================
        # CURRENT FILE
        # ====================================================

        self.current_file_label = QLabel(
            "Current: —"
        )

        self.current_file_label.setStyleSheet(
            """
            font-weight: bold;
            """
        )

        main_layout.addWidget(
            self.current_file_label
        )

        # ====================================================
        # PROGRESS BAR
        # ====================================================

        self.progress_bar = QProgressBar()

        self.progress_bar.setRange(
            0,
            100
        )

        self.progress_bar.setValue(
            0
        )

        main_layout.addWidget(
            self.progress_bar
        )

        # ====================================================
        # STATISTICS
        # ====================================================

        stats_layout = QHBoxLayout()

        self.progress_label = QLabel(
            "Ready"
        )

        self.stats_label = QLabel(
            "Success: 0    Failed: 0    Skipped: 0"
        )

        stats_layout.addWidget(
            self.progress_label
        )

        stats_layout.addStretch()

        stats_layout.addWidget(
            self.stats_label
        )

        main_layout.addLayout(
            stats_layout
        )

        # ====================================================
        # BOTTOM BUTTONS
        # ====================================================

        bottom_layout = QHBoxLayout()

        bottom_layout.addStretch()

        self.convert_button = QPushButton(
            "Convert All"
        )

        self.cancel_button = QPushButton(
            "Cancel"
        )

        self.convert_button.setMinimumSize(
            150,
            42
        )

        self.cancel_button.setMinimumSize(
            100,
            42
        )

        self.convert_button.setStyleSheet(
            """
            QPushButton {
                font-size: 14px;
                font-weight: bold;
            }
            """
        )

        self.cancel_button.setEnabled(
            False
        )

        self.convert_button.clicked.connect(
            self.start_conversion
        )

        self.cancel_button.clicked.connect(
            self.cancel_conversion
        )

        bottom_layout.addWidget(
            self.convert_button
        )

        bottom_layout.addWidget(
            self.cancel_button
        )

        main_layout.addLayout(
            bottom_layout
        )

        # ====================================================
        # STATUS BAR
        # ====================================================

        self.statusBar().showMessage(
            "Ready"
        )


    # ========================================================
    # ADD SINGLE DAV FILE
    # ========================================================

    def add_dav_file(
        self,
        file_path
    ):

        path = Path(
            file_path
        )

        # Must exist
        if not path.is_file():
            return

        # Must be DAV
        if path.suffix.lower() != ".dav":
            return

        # Convert to absolute path
        try:

            path = path.resolve()

        except Exception:

            pass

        # Prevent duplicate
        if path in self.dav_files:
            return

        # Add file
        self.dav_files.append(
            path
        )

        # ====================================================
        # AUTO DETECT CODEC
        # ====================================================

        try:

            data = path.read_bytes()

            codec = detect_codec(
                data
            )

            self.codec_cache[
                path
            ] = codec

        except Exception:

            self.codec_cache[
                path
            ] = None


    # ========================================================
    # ADD FILES
    # ========================================================

    def add_files(self):

        files, _ = (
            QFileDialog.getOpenFileNames(
                self,
                "Select DAV Files",
                "",
                "DAV Files (*.dav *.DAV);;All Files (*)"
            )
        )

        if not files:
            return

        self.statusBar().showMessage(
            "Adding DAV files..."
        )

        for file in files:

            self.add_dav_file(
                file
            )

        self.refresh_table()

        self.statusBar().showMessage(
            "Ready"
        )


    # ========================================================
    # ADD FOLDER
    # ========================================================

    def add_folder(self):

        folder = (
            QFileDialog.getExistingDirectory(
                self,
                "Select DAV Folder"
            )
        )

        if not folder:
            return

        folder_path = Path(
            folder
        )

        self.statusBar().showMessage(
            "Scanning DAV files..."
        )

        self.add_folder_files(
            folder_path
        )

        # Automatically suggest output folder
        if not self.output_edit.text().strip():

            output_folder = (
                folder_path
                /
                "Converted_MP4"
            )

            self.output_edit.setText(
                str(output_folder)
            )

        self.refresh_table()

        self.statusBar().showMessage(
            "Ready"
        )


    # ========================================================
    # SCAN FOLDER
    # ========================================================

    def add_folder_files(
        self,
        folder
    ):

        folder = Path(
            folder
        )

        try:

            files = sorted(
                file
                for file in folder.iterdir()
                if (
                    file.is_file()
                    and
                    file.suffix.lower()
                    == ".dav"
                )
            )

        except Exception as error:

            QMessageBox.warning(
                self,
                "Folder Error",
                str(error)
            )

            return

        for file in files:

            self.add_dav_file(
                file
            )


    # ========================================================
    # REFRESH TABLE
    # ========================================================

    def refresh_table(self):

        # Sort by filename
        self.dav_files.sort(
            key=lambda file:
            file.name.lower()
        )

        self.table.setRowCount(
            len(self.dav_files)
        )

        for row, file in enumerate(
            self.dav_files
        ):

            # =================================================
            # FILE NAME
            # =================================================

            file_item = QTableWidgetItem(
                file.name
            )

            # Hover shows full path
            file_item.setToolTip(
                str(file)
            )

            self.table.setItem(
                row,
                0,
                file_item
            )

            # =================================================
            # CODEC
            # =================================================

            codec = self.codec_cache.get(
                file
            )

            codec_text = codec_display_name(
                codec
            )

            codec_item = QTableWidgetItem(
                codec_text
            )

            self.table.setItem(
                row,
                1,
                codec_item
            )

            # =================================================
            # FILE SIZE
            # =================================================

            try:

                size = format_file_size(
                    file.stat().st_size
                )

            except Exception:

                size = "Unknown"

            self.table.setItem(
                row,
                2,
                QTableWidgetItem(
                    size
                )
            )

            # =================================================
            # STATUS
            # =================================================

            if codec is None:

                initial_status = (
                    "Unknown codec"
                )

            else:

                initial_status = (
                    "Waiting"
                )

            self.table.setItem(
                row,
                3,
                QTableWidgetItem(
                    initial_status
                )
            )

            # =================================================
            # TIME
            # =================================================

            self.table.setItem(
                row,
                4,
                QTableWidgetItem(
                    "—"
                )
            )

        # ====================================================
        # FILE COUNT
        # ====================================================

        total = len(
            self.dav_files
        )

        self.file_count_label.setText(
            f"{total} DAV file"
            +
            (
                ""
                if total == 1
                else "s"
            )
        )

        self.reset_statistics()


    # ========================================================
    # REMOVE SELECTED
    # ========================================================

    def remove_selected(self):

        rows = sorted(
            {
                item.row()
                for item
                in self.table.selectedItems()
            },
            reverse=True
        )

        if not rows:
            return

        for row in rows:

            if (
                0 <= row <
                len(self.dav_files)
            ):

                file = (
                    self.dav_files[
                        row
                    ]
                )

                # Remove codec cache
                self.codec_cache.pop(
                    file,
                    None
                )

                # Remove file
                del self.dav_files[
                    row
                ]

        self.refresh_table()


    # ========================================================
    # CLEAR FILES
    # ========================================================

    def clear_files(self):

        self.dav_files.clear()

        self.codec_cache.clear()

        self.refresh_table()

        self.statusBar().showMessage(
            "File list cleared"
        )


    # ========================================================
    # SELECT OUTPUT FOLDER
    # ========================================================

    def select_output_folder(self):

        folder = (
            QFileDialog.getExistingDirectory(
                self,
                "Select Output Folder"
            )
        )

        if folder:

            self.output_edit.setText(
                folder
            )


    # ========================================================
    # OPEN OUTPUT FOLDER
    # ========================================================

    def open_output_folder(self):

        output_text = (
            self.output_edit.text().strip()
        )

        if not output_text:

            QMessageBox.warning(
                self,
                "Output Folder",
                "Please select an output folder."
            )

            return

        folder = Path(
            output_text
        )

        try:

            folder.mkdir(
                parents=True,
                exist_ok=True
            )

            os.startfile(
                str(folder)
            )

        except Exception as error:

            QMessageBox.warning(
                self,
                "Open Folder",
                str(error)
            )


    # ========================================================
    # DRAG ENTER
    # ========================================================

    def dragEnterEvent(
        self,
        event: QDragEnterEvent
    ):

        if event.mimeData().hasUrls():

            event.acceptProposedAction()


    # ========================================================
    # DROP EVENT
    # ========================================================

    def dropEvent(
        self,
        event: QDropEvent
    ):

        added = False

        self.statusBar().showMessage(
            "Adding DAV files..."
        )

        for url in (
            event.mimeData().urls()
        ):

            path = Path(
                url.toLocalFile()
            )

            # =================================================
            # DAV FILE
            # =================================================

            if (
                path.is_file()
                and
                path.suffix.lower()
                == ".dav"
            ):

                self.add_dav_file(
                    path
                )

                added = True

            # =================================================
            # FOLDER
            # =================================================

            elif path.is_dir():

                self.add_folder_files(
                    path
                )

                # Suggest output folder
                if not self.output_edit.text().strip():

                    output_folder = (
                        path
                        /
                        "Converted_MP4"
                    )

                    self.output_edit.setText(
                        str(output_folder)
                    )

                added = True

        if added:

            self.refresh_table()

        self.statusBar().showMessage(
            "Ready"
        )

        event.acceptProposedAction()


    # ========================================================
    # START CONVERSION
    # ========================================================

    def start_conversion(self):

        # ====================================================
        # CHECK FILES
        # ====================================================

        if not self.dav_files:

            QMessageBox.warning(
                self,
                "No DAV Files",
                "Please add DAV files first."
            )

            return

        # ====================================================
        # CHECK OUTPUT
        # ====================================================

        output_text = (
            self.output_edit.text().strip()
        )

        if not output_text:

            QMessageBox.warning(
                self,
                "Output Folder",
                "Please select an output folder."
            )

            return

        output_folder = Path(
            output_text
        )

        try:

            output_folder.mkdir(
                parents=True,
                exist_ok=True
            )

        except Exception as error:

            QMessageBox.critical(
                self,
                "Output Folder Error",
                str(error)
            )

            return

        # ====================================================
        # RESET STATISTICS
        # ====================================================

        self.reset_statistics()

        # Reset status / time
        for row, file in enumerate(
            self.dav_files
        ):

            codec = self.codec_cache.get(
                file
            )

            if codec is None:

                status = "Unknown codec"

            else:

                status = "Waiting"

            self.table.setItem(
                row,
                3,
                QTableWidgetItem(
                    status
                )
            )

            self.table.setItem(
                row,
                4,
                QTableWidgetItem(
                    "—"
                )
            )

        # ====================================================
        # DISABLE UI
        # ====================================================

        self.set_controls_enabled(
            False
        )

        self.cancel_button.setEnabled(
            True
        )

        self.statusBar().showMessage(
            "Conversion running..."
        )

        # ====================================================
        # CREATE THREAD
        # ====================================================

        self.conversion_thread = (
            QThread()
        )

        self.conversion_worker = (
            ConversionWorker(
                list(
                    self.dav_files
                ),
                output_folder,
                self.skip_checkbox.isChecked()
            )
        )

        # Move worker into background thread
        self.conversion_worker.moveToThread(
            self.conversion_thread
        )

        # ====================================================
        # SIGNALS
        # ====================================================

        self.conversion_thread.started.connect(
            self.conversion_worker.run
        )

        self.conversion_worker.file_started.connect(
            self.file_started
        )

        self.conversion_worker.file_finished.connect(
            self.file_finished
        )

        self.conversion_worker.overall_finished.connect(
            self.conversion_finished
        )

        self.conversion_worker.overall_finished.connect(
            self.conversion_thread.quit
        )

        self.conversion_worker.overall_finished.connect(
            self.conversion_worker.deleteLater
        )

        self.conversion_thread.finished.connect(
            self.conversion_thread.deleteLater
        )

        # Start
        self.conversion_thread.start()


    # ========================================================
    # FILE STARTED
    # ========================================================

    def file_started(
        self,
        row,
        filename
    ):

        # Status
        self.table.setItem(
            row,
            3,
            QTableWidgetItem(
                "Converting..."
            )
        )

        # Current file
        self.current_file_label.setText(
            f"Current: {filename}"
        )

        # Status bar
        self.statusBar().showMessage(
            f"Converting {filename}"
        )


    # ========================================================
    # FILE FINISHED
    # ========================================================

    def file_finished(
        self,
        row,
        status,
        elapsed,
        error
    ):

        # ====================================================
        # STATUS
        # ====================================================

        status_item = QTableWidgetItem(
            status
        )

        # Full error shown as tooltip
        if error:

            status_item.setToolTip(
                error
            )

        self.table.setItem(
            row,
            3,
            status_item
        )

        # ====================================================
        # TIME
        # ====================================================

        if elapsed > 0:

            time_text = format_time(
                elapsed
            )

        else:

            time_text = "—"

        self.table.setItem(
            row,
            4,
            QTableWidgetItem(
                time_text
            )
        )

        # ====================================================
        # STATISTICS
        # ====================================================

        if status == "Completed":

            self.success_count += 1

        elif status == "Failed":

            self.failed_count += 1

        elif status == "Skipped":

            self.skipped_count += 1

        self.update_stats()

        # ====================================================
        # PROGRESS
        # ====================================================

        processed = (
            self.success_count
            +
            self.failed_count
            +
            self.skipped_count
        )

        total = len(
            self.dav_files
        )

        if total > 0:

            percentage = int(
                processed
                /
                total
                *
                100
            )

            self.progress_bar.setValue(
                percentage
            )

        self.progress_label.setText(
            f"{processed} / {total} processed"
        )


    # ========================================================
    # CONVERSION FINISHED
    # ========================================================

    def conversion_finished(
        self,
        success,
        failed,
        skipped,
        elapsed,
        cancelled
    ):

        # Re-enable UI
        self.set_controls_enabled(
            True
        )

        self.cancel_button.setEnabled(
            False
        )

        self.current_file_label.setText(
            "Current: —"
        )

        # ====================================================
        # CANCELLED
        # ====================================================

        if cancelled:

            title = (
                "Conversion Cancelled"
            )

            self.statusBar().showMessage(
                "Conversion cancelled"
            )

            message = (
                "Conversion was stopped.\n\n"
            )

        # ====================================================
        # COMPLETED
        # ====================================================

        else:

            title = (
                "Conversion Completed"
            )

            self.progress_bar.setValue(
                100
            )

            self.statusBar().showMessage(
                "Conversion completed"
            )

            message = (
                "All files have been processed.\n\n"
            )

        # ====================================================
        # RESULT
        # ====================================================

        message += (
            f"Successful: {success}\n"
            f"Failed: {failed}\n"
            f"Skipped: {skipped}\n\n"
            f"Total time: "
            f"{format_time(elapsed)}"
        )

        QMessageBox.information(
            self,
            title,
            message
        )

        # Remove references
        self.conversion_worker = None
        self.conversion_thread = None


    # ========================================================
    # CANCEL CONVERSION
    # ========================================================

    def cancel_conversion(self):

        if self.conversion_worker:

            self.conversion_worker.cancel()

            self.cancel_button.setEnabled(
                False
            )

            self.progress_label.setText(
                "Stopping after current file..."
            )

            self.statusBar().showMessage(
                "Cancellation requested..."
            )


    # ========================================================
    # DOUBLE CLICK ROW
    # ========================================================

    def table_double_click(
        self,
        row,
        column
    ):

        if (
            row < 0
            or
            row >= len(self.dav_files)
        ):

            return

        output_text = (
            self.output_edit.text().strip()
        )

        if not output_text:
            return

        dav_file = (
            self.dav_files[
                row
            ]
        )

        mp4_file = (
            Path(
                output_text
            )
            /
            f"{dav_file.stem}.mp4"
        )

        if not mp4_file.exists():

            self.statusBar().showMessage(
                "Converted MP4 does not exist."
            )

            return

        try:

            os.startfile(
                str(mp4_file)
            )

        except Exception as error:

            QMessageBox.warning(
                self,
                "Open Video",
                str(error)
            )


    # ========================================================
    # RESET STATISTICS
    # ========================================================

    def reset_statistics(self):

        self.success_count = 0
        self.failed_count = 0
        self.skipped_count = 0

        self.progress_bar.setValue(
            0
        )

        self.progress_label.setText(
            "Ready"
        )

        self.current_file_label.setText(
            "Current: —"
        )

        self.update_stats()


    # ========================================================
    # UPDATE STATISTICS
    # ========================================================

    def update_stats(self):

        self.stats_label.setText(
            f"Success: {self.success_count}    "
            f"Failed: {self.failed_count}    "
            f"Skipped: {self.skipped_count}"
        )


    # ========================================================
    # ENABLE / DISABLE CONTROLS
    # ========================================================

    def set_controls_enabled(
        self,
        enabled
    ):

        self.add_files_button.setEnabled(
            enabled
        )

        self.add_folder_button.setEnabled(
            enabled
        )

        self.remove_button.setEnabled(
            enabled
        )

        self.clear_button.setEnabled(
            enabled
        )

        self.output_edit.setEnabled(
            enabled
        )

        self.output_browse_button.setEnabled(
            enabled
        )

        self.skip_checkbox.setEnabled(
            enabled
        )

        self.convert_button.setEnabled(
            enabled
        )


# ============================================================
# APPLICATION
# ============================================================

if __name__ == "__main__":

    app = QApplication(
        sys.argv
    )

    window = MainWindow()

    window.show()

    sys.exit(
        app.exec()
    )