import sys
import os
import requests
import threading
import re

from aerobull_api import (
    app,
    selected_row_data,
    latest_rotabull_import,
    part_lookup_request,
    manual_selection_required,
    paperwork_settings,
    no_quote_parts
)

from urllib.parse import urlparse

from openpyxl import load_workbook

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QLabel,
    QLineEdit,
    QFileDialog,
    QProgressBar,
    QMessageBox,
    QCheckBox
)

from PySide6.QtGui import (
    QColor,
    QPixmap
)

from PySide6.QtCore import (
    QTimer,
    Qt
)

from parser import parse_rotabull

# To ensure that saved ppw files are accepted by Windows

def safe_filename(text):

    return re.sub(
        r'[<>:"/\\|?*]',
        '_',
        str(text)
    )

# Logo is hosted remotely so it doesn't need to ship/be updated alongside the
# app itself. It's cached locally on first successful download so later
# launches don't depend on network access, and so a slow/unreachable host
# only costs a few seconds once rather than on every start.

LOGO_URL = (
    "https://raw.githubusercontent.com/"
    "vpociuskillickaerospace/Aerobull_Logo/"
    "main/AeroBull.png"
)

LOGO_CACHE_PATH = os.path.join(
    os.getenv(
        "LOCALAPPDATA",
        os.path.expanduser("~")
    ),
    "AeroBull",
    "AeroBull.png"
)

def get_logo_path():

    os.makedirs(
        os.path.dirname(LOGO_CACHE_PATH),
        exist_ok=True
    )

    try:

        response = requests.get(
            LOGO_URL,
            timeout=5
        )

        response.raise_for_status()

        with open(LOGO_CACHE_PATH, "wb") as f:
            f.write(response.content)

    except Exception as e:

        print("Logo download failed, falling back to cache:", e)

    return (
        LOGO_CACHE_PATH
        if os.path.exists(LOGO_CACHE_PATH)
        else None
    )

class AeroBullWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.setWindowTitle("AeroBull")
        self.resize(1400, 800)

        widget = QWidget()
        self.setCentralWidget(widget)

        layout = QVBoxLayout(widget)
        
        header_layout = QVBoxLayout()
        layout.addLayout(header_layout)
        
        main_layout = QHBoxLayout()
        layout.addLayout(main_layout)
        
        left_layout = QVBoxLayout()

        right_layout = QVBoxLayout()
        
        logo = QLabel()

        logo_path = get_logo_path()

        if logo_path:

            pixmap = QPixmap(logo_path)

            logo.setPixmap(
                pixmap.scaled(
                    950,
                    480,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            )

        else:

            logo.setText("AeroBull")

        header_layout.addWidget(
            logo
        )

        main_layout.addLayout(
            left_layout,
            stretch=4
        )

        main_layout.addLayout(
            right_layout,
            stretch=1
        )    
        
        right_layout.addSpacing(20)
        
        self.quote_number_input = QLineEdit()

        quote_label = QLabel(
            "Quantum Quote Reference"
        )

        quote_label.setAlignment(
            Qt.AlignCenter
        )

        right_layout.addWidget(
            quote_label
        )
        
        right_layout.addWidget(
            self.quote_number_input
        )
        
        self.include_paperwork_checkbox = QCheckBox(
            "Include Paperwork URL in Comments"
        )

        self.include_paperwork_checkbox.setChecked(False)
        
        self.include_paperwork_checkbox.stateChanged.connect(
            self.refresh_dataframe
        )
        
        right_layout.addWidget(
            self.include_paperwork_checkbox
        )

        right_layout.addSpacing(40)

        self.quote_number_input.textChanged.connect(
            self.update_quote_numbers
        )
        
        export_button = QPushButton(
            "Push To Excel"
        )
        
        export_button.setStyleSheet("""
            QPushButton {
                background-color: #00594C;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                padding: 6px;
            }

            QPushButton:hover {
                background-color: #007261;
            }

            QPushButton:pressed {
                background-color: #00463B;
            }
        """)


        export_button.clicked.connect(
            self.push_to_excel
        )
        
        download_button = QPushButton(
            "Download Paperwork"
        )
        
        download_button.setStyleSheet("""
            QPushButton {
                background-color: #00594C;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                padding: 6px;
            }

            QPushButton:hover {
                background-color: #007261;
            }

            QPushButton:pressed {
                background-color: #00463B;
            }
        """)

        download_button.clicked.connect(
            self.download_paperwork
        )

        right_layout.addWidget(
            download_button
        )
        
        self.progress_bar = QProgressBar()

        self.progress_bar.setMinimum(0)
        self.progress_bar.setValue(0)

        right_layout.addWidget(
            self.progress_bar
        )
        
        right_layout.addSpacing(20)

        right_layout.addWidget(
            export_button
        )
        
        right_layout.addSpacing(200)
        
        footer_note = QLabel(
            "AeroBull version 1.0 BETA. Evaluation version for use by Killick Aerospace only. © Adam Kuitkowski 2026." 
        )
        footer_note.setStyleSheet("""
            font-size: 8pt;
        """)
        footer_note.setAlignment(
            Qt.AlignLeft
        )
        footer_note.setWordWrap(True)
        
        right_layout.addWidget(
            footer_note
        )

        self.table = QTableWidget()
        self.table.itemSelectionChanged.connect(
            self.publish_selected_row
        )

        left_layout.addWidget(
            self.table
        )

        
        self.import_timer = QTimer()

# This is part of the Auto form-fill feature
# Aerobull checks every second whether the Edge extension has sent a PN Lookup request

        self.import_timer.timeout.connect(
            self.check_for_imports
        )

        self.import_timer.start(1000)
        
        right_layout.addStretch()

    def process_imported_html(self, html):

 #disables imports if quote is not from Killick Aerospace

        if (
            "quote from killick aerospace"
            not in html.lower()
        ):

            QMessageBox.warning(
                self,
                "Import Rejected",
                "This RFQ does not originate from Killick Aerospace."
            )

            return

        self.load_quote(
            html,
            html
        )

        if not self.current_df.empty:

            self.original_quote_number = (
                self.current_df.iloc[0]["Quote Number"]
            )

    def load_quote(
        self,
        text,
        html
    ):
        self.last_imported_text = text
        self.last_imported_html = html

        df = parse_rotabull(
            text,
            html,
            include_paperwork_url=
                self.include_paperwork_checkbox.isChecked()
        )

        self.current_df = df
        
        no_quote_parts.clear()

        no_quote_parts.extend(

            df[
                df["Price"]
                .astype(str)
                .str.strip()
                .eq("-")
            ]["Part Number"]
            .astype(str)
            .tolist()
        )

        self.load_dataframe(df)
        

    def load_dataframe(self, df):

        self.table.setRowCount(
            len(df)
        )

        self.table.setColumnCount(
            len(df.columns)
        )

        self.table.setHorizontalHeaderLabels(
            list(df.columns)
        )

        for r in range(len(df)):

            no_quote = (
                str(
                    df.iloc[r]["Price"]
                ).strip() == "-"
            )

            for c in range(len(df.columns)):

                item = QTableWidgetItem(
                    str(
                        df.iloc[r, c]
                    )
                )

# Grey out the no-quotes. NQs are identified when "Price" = "-"

                if no_quote:

                    item.setBackground(
                        QColor(
                            180,
                            180,
                            180
                        )
                    )

                self.table.setItem(
                    r,
                    c,
                    item
                )

        self.table.resizeColumnsToContents()
   
# Below function updates the dataframe if the user checks/unchecks the 'append ppw URL to comments' box
   
    def refresh_dataframe(self):

        if not hasattr(
            self,
            "last_imported_html"
        ):
            return

        self.load_quote(
            self.last_imported_text,
            self.last_imported_html
        )
        
        self.update_quote_numbers()
    
 # Allow user to input custom quote number (eg Quantum reference)   
    
    def update_quote_numbers(self):

        quote_number = (
            self.quote_number_input.text().strip()
            or self.original_quote_number
        )

        if not hasattr(
            self,
            "current_df"
        ):
            return

        self.current_df[
            "Quote Number"
        ] = quote_number

        self.load_dataframe(
            self.current_df
        )
   
# Below function handles both Edge extension part requests and Rotabull exports
   
    def check_for_imports(self):
        
        part_number = (
            part_lookup_request[
                "part_number"
            ]
        )

        if part_number:

            self.handle_part_lookup(
                part_number
            )

            part_lookup_request[
                "part_number"
            ] = ""

        html = latest_rotabull_import["html"]

        if not html:
            return

        latest_rotabull_import["html"] = ""

        self.process_imported_html(html)
        
    
    def push_to_excel(self):

        if self.table.rowCount() == 0:

            QMessageBox.warning(
                self,
                "No Data",
                "Nothing to export."
            )

            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Excel Workbook",
            "",
            "Excel Files (*.xlsx)"
        )

        if not file_path:
            return

        try:

            wb = load_workbook(file_path)
            ws = wb.active

            quote_number = (
                self.quote_number_input.text().strip()
                or self.original_quote_number
            )

            ws["C1"] = quote_number

            column_map = {
                "Quote Number": "S",
                "Part Number": "T",
                "Keyword": "V",
                "Quantity": "W",
                "Unit": "X",
                "Price": "Y",
                "Currency": "Z",
                "Price Held Firm": "AA",
                "Lead Time Days": "AB",
                "Serial Number": "AC",
                "Condition": "AF",
                "Warranty Period": "AL",
                "Warranty Ref Code": "AM",
                "Warranty Type Code": "AN",
                "Supplier Remarks": "AU",
                "Comments": "AV",
                "Tagged By": "BC",
                "Tag Date": "BE"
            }

            headers = {
                self.table
                .horizontalHeaderItem(col)
                .text(): col

                for col in range(
                    self.table.columnCount()
                )
            }

            for r in range(
                self.table.rowCount()
            ):

                excel_row = r + 4

                for field, excel_col in (
                    column_map.items()
                ):

                    if field not in headers:
                        continue

                    item = self.table.item(
                        r,
                        headers[field]
                    )

                    value = (
                        item.text()
                        if item
                        else ""
                    )

                    if field == "Quote Number":
                        value = quote_number

                    ws[
                        f"{excel_col}{excel_row}"
                    ] = value

            wb.save(file_path)

            QMessageBox.information(
                self,
                "Success",
                "Data exported successfully."
            )

        except Exception as e:

            QMessageBox.critical(
                self,
                "Export Failed",
                str(e)
            )
        
    def publish_selected_row(self):

        selected_items = (
            self.table.selectedItems()
        )

        if not selected_items:
            return

        selected_row = (
            selected_items[0].row()
        )

        if selected_row < 0:
            return

        row_data = {}
        
        excluded_columns = {
            "Paperwork1",
            "Paperwork2",
            "Paperwork3"
        }

        for col in range(
            self.table.columnCount()
        ):

            header = (
                self.table
                .horizontalHeaderItem(col)
                .text()
            )
            
            if header in excluded_columns:
                continue

            item = self.table.item(
                selected_row,
                col
            )

            row_data[header] = (
                item.text()
                if item
                else ""
            )

        selected_row_data.clear()

        selected_row_data.update(
            row_data
        )
    def download_paperwork(self):

        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Download Folder"
        )

        if not folder:
            return
            
        paperwork_settings["folder"] = folder

        paperwork_columns = [
            "Paperwork1",
            "Paperwork2",
            "Paperwork3"
        ]

        headers = {}

        for col in range(
            self.table.columnCount()
        ):

            header = (
                self.table
                .horizontalHeaderItem(col)
                .text()
            )

            headers[header] = col

        total_files = 0

        for row in range(
            self.table.rowCount()
        ):

            for column_name in paperwork_columns:

                if column_name not in headers:
                    continue

                item = self.table.item(
                    row,
                    headers[column_name]
                )

                if (
                    item and
                    item.text().strip()
                ):
                    total_files += 1

        self.progress_bar.setMaximum(
            total_files
        )

        self.progress_bar.setValue(0)

        download_count = 0
        skipped_count = 0
        processed_count = 0

        for row in range(
            self.table.rowCount()
        ):

            for column_name in paperwork_columns:

                if column_name not in headers:
                    continue

                col = headers[column_name]

                item = self.table.item(
                    row,
                    col
                )

                if not item:
                    continue

                url = item.text().strip()

                if not url:
                    continue

                try:

                    part_col = headers[
                        "Part Number"
                    ]

                    serial_col = headers[
                        "Serial Number"
                    ]

                    part_item = self.table.item(
                        row,
                        part_col
                    )

                    serial_item = self.table.item(
                        row,
                        serial_col
                    )

                    part_number = safe_filename(
                        part_item.text().strip()
                    ) if part_item else "UNKNOWN_PART"

                    serial_number = safe_filename(
                        serial_item.text().strip()
                    ) if serial_item else "NOSERIAL"

                    paperwork_number = (
                        column_name.replace(
                            "Paperwork",
                            ""
                        )
                    )

                    extension = (
                        os.path.splitext(
                            urlparse(url).path
                        )[1]
                    )

                    if not extension:
                        extension = ".pdf"

                    filename = (
                        f"{part_number}_"
                        f"{serial_number}_"
                        f"{paperwork_number}"
                        f"{extension}"
                    )

                    filepath = os.path.join(
                        folder,
                        filename
                    )

                    if os.path.exists(
                        filepath
                    ):

                        skipped_count += 1

                    else:

                        response = requests.get(
                            url,
                            timeout=30
                        )

                        response.raise_for_status()

                        with open(
                            filepath,
                            "wb"
                        ) as f:

                            f.write(
                                response.content
                            )

                        download_count += 1

                except Exception as e:

                    print(
                        f"Failed: {url}"
                    )

                    print(e)

                processed_count += 1

                self.progress_bar.setValue(
                    processed_count
                )

                QApplication.processEvents()

        QMessageBox.information(
            self,
            "Download Complete",
            f"{download_count} file(s) downloaded.\n"
            f"{skipped_count} file(s) skipped."
        )


        
    def handle_part_lookup(
        self,
        part_number
    ):

        if not hasattr(
            self,
            "current_df"
        ):
            return

        matches = self.current_df[
            self.current_df[
                "Part Number"
            ]
            .str.upper()
            ==
            part_number.upper()
        ]

        if len(matches) == 0:
            
            part_lookup_request[
                "result"
            ] = {
                "found": False,
                "multiple": False
            }

            return

# If there are multiple results for a single part number, the user must manually select the line to be pushed to Aeroxchange

        if len(matches) > 1:

            manual_selection_required[
                "required"
            ] = True

            part_lookup_request["result"] = {
                "found": False,
                "multiple": True
            }

            return

        table_row = matches.index[0]

        row = matches.iloc[0].to_dict()
    
# Below ensures that the user-specified custom quote number is preserved when filling the form
    
        custom_quote = (
            self.quote_number_input
            .text()
            .strip()
        )

        if custom_quote:
            row["Quote Number"] = custom_quote

        part_lookup_request[
            "result"
        ] = {
            "found": True,
            "multiple": False,
            "data": row
        }
    
if __name__ == "__main__":

    qt_app = QApplication(sys.argv)
    
    def run_api():
        
        print("Starting AeroBull API...")

        app.run(
            host="127.0.0.1",
            port=8765,
            debug=False,
            use_reloader=False
        )


    api_thread = threading.Thread(
        target=run_api,
        daemon=True
    )

    api_thread.start()

    window = AeroBullWindow()
    window.show()

    sys.exit(qt_app.exec())