"""Shared desktop theme."""
from pathlib import Path
STYLE = """
QWidget { background: #0d121a; color: #e9eef6; font-family: 'Segoe UI'; font-size: 10pt; }
QMainWindow, QDialog { background: #0d121a; }
QLabel { background: transparent; }
QWidget#rail { background: #101720; border-right: 1px solid #243040; }
QWidget#content { background: #0d121a; }
QLabel#brand { font-size: 22pt; font-weight: 700; color: #69e5cb; }
QLabel#eyebrow { color: #69e5cb; font-size: 9pt; font-weight: 600; }
QLabel#heading { font-size: 25pt; font-weight: 650; }
QLabel#pageTitle { font-size: 22pt; font-weight: 650; }
QLabel#metric { font-size: 30pt; font-weight: 600; }
QLabel#muted { color: #93a5ba; }
QLabel#status { background: #151e2a; color: #b8cadb; border: 1px solid #253347; border-radius: 8px; padding: 10px 14px; }
QLabel#chip { background: #1b2834; color: #a2e9da; padding: 6px 10px; border-radius: 6px; }
QGroupBox { background: #131c27; border: 1px solid #273447; border-radius: 12px; margin-top: 12px; padding: 22px 18px 16px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 18px; padding: 0 7px; color: #b7c9df; }
QGroupBox QWidget { background: transparent; }
QGroupBox QProgressBar { background: #233143; }
QGroupBox QLineEdit, QGroupBox QComboBox, QGroupBox QSpinBox, QGroupBox QDoubleSpinBox, QGroupBox QPlainTextEdit { background: #0b121c; }
QPushButton { background: #233145; border: 1px solid #364a62; border-radius: 7px; padding: 10px 14px; font-weight: 500; }
QPushButton:hover { background: #2b4056; border-color: #5e819f; }
QPushButton:pressed { background: #172738; }
QPushButton:disabled { background: #18212d; color: #586b82; border-color: #263445; }
QPushButton#primary { background: #60dcc3; color: #0b2926; border: 1px solid #86eed8; font-weight: 650; }
QPushButton#primary:hover { background: #87efd7; }
QPushButton#primary:disabled { background: #203c3c; color: #6f9590; border-color: #2d514e; }
QPushButton#record { background: #392735; border-color: #785164; color: #ffd7e0; }
QPushButton#record[active='true'] { background: #8d354b; border-color: #ff91a7; color: white; }
QPushButton#record:disabled { background: #211e2a; color: #827180; border-color: #3b3446; }
QPushButton#nav { text-align: left; border: 0; background: transparent; padding: 13px 16px; color: #9baec5; }
QPushButton#nav:hover { background: #192637; color: white; }
QPushButton#nav:checked { background: #203b3b; color: #7be8d0; font-weight: 650; border-left: 3px solid #69e5cb; }
QPushButton#quiet { background: transparent; color: #9eb3cc; border: 1px solid #293a4d; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QListWidget, QTableWidget { background: #0b121c; border: 1px solid #2c3e53; border-radius: 6px; padding: 7px; selection-background-color: #245b59; selection-color: #e8fff9; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: #69dfc7; }
QComboBox QAbstractItemView { background: #182535; selection-background-color: #2e5558; }
QComboBox::drop-down { width: 22px; border: 0; }
QPlainTextEdit { color: #a8bbd0; font-size: 9pt; }
QListWidget::item { padding: 10px; border-bottom: 1px solid #233143; }
QListWidget::item:selected { background: #233f4b; border-radius: 5px; }
QTabWidget::pane { border: 0; padding: 8px 0 0; }
QTabBar::tab { background: #151f2c; color: #99aec6; padding: 10px 16px; margin-right: 5px; border-radius: 5px; }
QTabBar::tab:selected { background: #25403f; color: #89ead6; }
QProgressBar { background: #233143; border: 0; border-radius: 4px; min-height: 7px; max-height: 9px; }
QProgressBar::chunk { background: #62d9c0; border-radius: 4px; }
QSlider::groove:horizontal { background: #2a3e53; height: 5px; border-radius: 2px; }
QSlider::handle:horizontal { background: #73e4cd; width: 14px; margin: -5px 0; border-radius: 6px; }
QHeaderView::section { background: #203044; color: #dce9f7; padding: 9px; border: 0; border-right: 1px solid #304359; font-weight: 600; }
QTableCornerButton::section { background: #203044; border: 0; }
QCheckBox { spacing: 9px; }
QCheckBox::indicator { width: 18px; height: 18px; border: 2px solid #60778f; border-radius: 4px; background: #0e1722; }
QCheckBox::indicator:checked { background: #64dfc5; border-color: #a2f4e1; }
QScrollArea { border: 0; }
QScrollBar:vertical { background: #111b27; width: 9px; margin: 0; }
QScrollBar::handle:vertical { background: #3b5168; border-radius: 4px; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QMenuBar { background: #101720; color: #9fb2c9; }
QMenuBar::item:selected, QMenu::item:selected { background: #254a49; color: white; }
QMenu { background: #172332; border: 1px solid #354b62; padding: 5px; }
QMenu::item { padding: 8px 26px; }
QToolTip { background: #243546; color: white; border: 1px solid #57778e; padding: 6px; }
"""

assets = (Path(__file__).resolve().parent/'assets').as_posix()
STYLE += '''
QComboBox::down-arrow { image: url("ASSETS/chevron_down.svg"); width: 12px; height: 8px; }
QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 20px; border-left: 1px solid #2c3e53; }
QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 20px; border-left: 1px solid #2c3e53; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url("ASSETS/chevron_up.svg"); width: 8px; height: 5px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url("ASSETS/chevron_down.svg"); width: 8px; height: 5px; }
'''.replace('ASSETS', assets)
