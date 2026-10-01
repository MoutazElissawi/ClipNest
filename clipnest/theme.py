"""Shared desktop theme."""
from pathlib import Path
STYLE = """
QWidget { background: #191919; color: #efefef; font-family: 'Segoe UI'; font-size: 10pt; }
QMainWindow, QDialog { background: #191919; }
QLabel { background: transparent; }
QWidget#rail { background: #1f1f1f; border-right: 1px solid #414141; }
QWidget#content { background: #191919; }
QLabel#brand { font-size: 18pt; font-weight: 700; color: #efefef; }
QLabel#eyebrow { color: #76b900; font-size: 9pt; font-weight: 600; }
QLabel#heading { font-size: 20pt; font-weight: 650; }
QLabel#pageTitle { font-size: 20pt; font-weight: 650; }
QLabel#metric { font-size: 22pt; font-weight: 600; }
QLabel#muted { color: #bcbcbc; }
QLabel#status { background: #282828; color: #cacaca; border: 1px solid #555555; border-radius: 8px; padding: 8px 12px; }
QLabel#chip { background: #282828; color: #a4d65e; padding: 6px 10px; border-radius: 6px; }
QGroupBox { background: transparent; border: 0; border-top: 1px solid #474747; border-radius: 0; margin-top: 8px; padding: 16px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 16px; padding: 0 7px; color: #cacaca; }
QGroupBox QWidget { background: transparent; }
QGroupBox QProgressBar { background: #323232; }
QGroupBox QLineEdit, QGroupBox QComboBox, QGroupBox QSpinBox, QGroupBox QDoubleSpinBox, QGroupBox QPlainTextEdit { background: #161616; }
QPushButton { background: #353535; border: 1px solid #696969; border-radius: 4px; padding: 8px 12px; font-weight: 500; }
QPushButton:hover { background: #434343; border-color: #9d9d9d; }
QPushButton:pressed { background: #272727; }
QPushButton:disabled { background: #222222; color: #959595; border-color: #353535; }
QPushButton#primary { background: #76b900; color: #76b900; border: 1px solid #a4d65e; font-weight: 650; }
QPushButton#primary:hover { background: #a4d65e; }
QPushButton#primary:disabled { background: #76b900; color: #76b900; border-color: #76b900; }
QPushButton#record { background: #392735; border-color: #785164; color: #ffd7e0; }
QPushButton#record[active='true'] { background: #8d354b; border-color: #ff91a7; color: white; }
QPushButton#record:disabled { background: #232323; color: #827180; border-color: #3c3c3c; }
QPushButton#nav { text-align: left; border: 0; background: transparent; padding: 12px 16px; color: #c3c3c3; }
QPushButton#nav:hover { background: #272727; color: white; }
QPushButton#nav:checked { background: #76b900; color: #a4d65e; font-weight: 650; border-left: 3px solid #76b900; }
QPushButton#quiet { background: transparent; color: #c3c3c3; border: 1px solid #6d6d6d; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QListWidget, QTableWidget { background: #161616; border: 1px solid #6d6d6d; border-radius: 6px; padding: 7px; selection-background-color: #76b900; selection-color: #f5f5f5; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: #76b900; }
QComboBox QAbstractItemView { background: #262626; selection-background-color: #76b900; }
QComboBox::drop-down { width: 22px; border: 0; }
QPlainTextEdit { color: #bcbcbc; font-size: 9pt; }
QListWidget::item { padding: 10px; border-bottom: 1px solid #323232; }
QListWidget::item:selected { background: #76b900; border-radius: 5px; }
QTabWidget::pane { border: 0; padding: 8px 0 0; }
QTabBar::tab { background: #282828; color: #c3c3c3; padding: 10px 16px; margin-right: 5px; border-radius: 5px; }
QTabBar::tab:selected { background: #76b900; color: #a4d65e; }
QProgressBar { background: #323232; border: 0; border-radius: 4px; min-height: 7px; max-height: 9px; }
QProgressBar::chunk { background: #76b900; border-radius: 4px; }
QSlider::groove:horizontal { background: #3e3e3e; height: 5px; border-radius: 2px; }
QSlider::handle:horizontal { background: #76b900; width: 14px; margin: -5px 0; border-radius: 6px; }
QHeaderView::section { background: #313131; color: #e9e9e9; padding: 9px; border: 0; border-right: 1px solid #444444; font-weight: 600; }
QTableCornerButton::section { background: #313131; border: 0; }
QCheckBox { spacing: 9px; }
QCheckBox::indicator { width: 18px; height: 18px; border: 2px solid #777777; border-radius: 4px; background: #181818; }
QCheckBox::indicator:checked { background: #76b900; border-color: #a4d65e; }
QScrollArea { border: 0; }
QScrollBar:vertical { background: #1c1c1c; width: 9px; margin: 0; }
QScrollBar::handle:vertical { background: #515151; border-radius: 4px; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QMenuBar { background: #1f1f1f; color: #b3b3b3; }
QMenuBar::item:selected, QMenu::item:selected { background: #76b900; color: white; }
QMenu { background: #242424; border: 1px solid #4b4b4b; padding: 5px; }
QMenu::item { padding: 8px 26px; }
QToolTip { background: #353535; color: white; border: 1px solid #747474; padding: 6px; }
"""

assets = (Path(__file__).resolve().parent/'assets').as_posix()
STYLE += '''
QComboBox::down-arrow { image: url("ASSETS/chevron_down.svg"); width: 12px; height: 8px; }
QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 20px; border-left: 1px solid #6d6d6d; }
QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 20px; border-left: 1px solid #6d6d6d; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url("ASSETS/chevron_up.svg"); width: 8px; height: 5px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url("ASSETS/chevron_down.svg"); width: 8px; height: 5px; }
'''.replace('ASSETS', assets)

STYLE += """
QPushButton:focus { border: 2px solid #a4d65e; }
QSlider:focus { border: 1px solid #a4d65e; }
QCheckBox:focus { outline: 1px solid #a4d65e; }
QLabel#eyebrow { color: #c3c3c3; font-size: 10pt; }
QLabel#chip { background: transparent; color: #cccccc; padding: 4px 0; border-radius: 0; }
"""

STYLE += """
QWidget, QMainWindow, QDialog, QWidget#content { background: #101010; color: #eeeeee; }
QLabel { background: transparent; }
QWidget#rail { background: #161616; border-right: 1px solid #363636; }
QPushButton#primary, QPushButton#transport { background: #76b900; color: #101500; border: 1px solid #76b900; }
QPushButton#primary:hover, QPushButton#transport:hover { background: #8ed000; border-color: #8ed000; }
QPushButton#primary:disabled { background: #29351b; color: #95a480; border-color: #3d4b2e; }
QPushButton#nav:checked { background: #253018; color: #a4d65e; border-left: 3px solid #76b900; }
QPushButton#nav:hover { background: #292929; }
QGroupBox { background: transparent; }
QPushButton#compact { padding: 4px; }
QPushButton#transport { padding: 4px; }
QTabBar::tab:selected { background: #29351b; color: #a4d65e; }
QMenuBar::item:selected, QMenu::item:selected { background: #29351b; color: #eeeeee; }
"""
