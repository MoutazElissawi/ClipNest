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
QPushButton { outline: 0; background: #353535; border: 1px solid #696969; border-radius: 4px; padding: 8px 12px; font-weight: 500; }
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
QPushButton:focus { border-color: #a4d65e; }
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

# Suppress the native dotted text rectangle while retaining visible focus.
# Named button rules above outrank generic :focus, so cover them explicitly.
STYLE += """
QPushButton#quiet:focus, QPushButton#compact:focus,
QPushButton#record:focus { border-color: #a4d65e; }
QPushButton#primary:focus, QPushButton#transport:focus { border-color: #eeeeee; }
QPushButton#nav:focus { background: #354822; color: #ffffff; }
"""

# Optional frosted-glass appearance. This intentionally builds on the normal
# dark theme so every control keeps a readable fallback even when the native
# Windows backdrop API is unavailable.
GLASS_STYLE = STYLE + r"""
QWidget { background: transparent; }
QMainWindow { background: transparent; }
QDialog { background: rgba(14, 22, 19, 245); }
QWidget#shell { background: transparent; }
QWidget#content { background: transparent; }
QWidget#rail {
    background: rgba(10, 17, 15, 88);
    border-right: 1px solid rgba(255, 255, 255, 40);
}
QLabel#brand { color: #f7f8f6; font-size: 18pt; font-weight: 700; }
QLabel#pageTitle { color: #f8f9f7; font-size: 21pt; font-weight: 700; }
QLabel#metric { color: #ffffff; font-size: 23pt; font-weight: 650; }
QLabel#muted { color: rgba(236, 241, 237, 175); }
QLabel#status {
    background: rgba(255, 255, 255, 18);
    color: #eef3ef;
    border: 1px solid rgba(255, 255, 255, 55);
    border-radius: 12px;
    padding: 10px 14px;
}
QLabel#chip { color: rgba(240, 244, 241, 205); }
QGroupBox {
    background: rgba(130, 160, 145, 24);
    border: 1px solid rgba(255, 255, 255, 52);
    border-radius: 14px;
    margin-top: 12px;
    padding: 20px 16px 16px 16px;
    font-weight: 650;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    top: 2px;
    padding: 0 7px;
    color: #f3f6f3;
    background: transparent;
}
QGroupBox QWidget { background: transparent; }
QPushButton {
    background: rgba(255, 255, 255, 18);
    border: 1px solid rgba(255, 255, 255, 62);
    border-radius: 9px;
    color: #f4f6f4;
    padding: 8px 12px;
}
QPushButton:hover { background: rgba(255, 255, 255, 31); border-color: rgba(255, 255, 255, 100); }
QPushButton:pressed { background: rgba(0, 0, 0, 70); }
QPushButton:disabled { background: rgba(255, 255, 255, 8); color: rgba(235, 240, 236, 100); border-color: rgba(255, 255, 255, 25); }
QPushButton#quiet { background: rgba(255, 255, 255, 10); color: #eef2ee; border: 1px solid rgba(255, 255, 255, 58); }
QPushButton#nav { background: transparent; border: 0; border-radius: 9px; color: rgba(239, 244, 240, 205); }
QPushButton#nav:hover { background: rgba(255, 255, 255, 18); color: white; }
QPushButton#nav:checked {
    background: rgba(91, 211, 43, 24);
    color: #c8ff75;
    border-left: 3px solid #91f128;
    font-weight: 650;
}
QPushButton#primary, QPushButton#transport {
    background: rgba(147, 241, 40, 230);
    color: #102000;
    border: 1px solid rgba(193, 255, 119, 240);
    border-radius: 9px;
}
QPushButton#primary:hover, QPushButton#transport:hover { background: rgba(168, 255, 64, 245); border-color: #d8ff9e; }
QPushButton#record { background: rgba(89, 35, 57, 130); border-color: rgba(255, 145, 167, 100); }
QPushButton#record[active='true'] { background: rgba(141, 53, 75, 210); border-color: #ff91a7; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QListWidget, QTableWidget {
    background: rgba(4, 9, 8, 70);
    color: #f1f4f1;
    border: 1px solid rgba(255, 255, 255, 55);
    border-radius: 9px;
    padding: 7px;
    selection-background-color: rgba(118, 185, 0, 210);
    selection-color: #ffffff;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: rgba(164, 214, 94, 220); }
QComboBox QAbstractItemView { background: rgba(18, 27, 24, 245); border: 1px solid rgba(255,255,255,55); selection-background-color: rgba(67, 99, 38, 235); }
QTabBar::tab { background: rgba(255, 255, 255, 14); color: rgba(240,244,241,190); border: 1px solid rgba(255,255,255,26); border-radius: 8px; }
QTabBar::tab:selected { background: rgba(118, 185, 0, 44); color: #c7ff79; border-color: rgba(164,214,94,85); }
QProgressBar { background: rgba(255, 255, 255, 21); border-radius: 4px; }
QProgressBar::chunk { background: #9cf236; border-radius: 4px; }
QSlider::groove:horizontal { background: rgba(255,255,255,45); }
QSlider::handle:horizontal { background: #9cf236; }
QHeaderView::section { background: rgba(255,255,255,18); color: #eef2ee; border-right: 1px solid rgba(255,255,255,28); }
QTableCornerButton::section { background: rgba(255,255,255,18); border: 0; }
QCheckBox::indicator { background: rgba(0,0,0,80); border-color: rgba(255,255,255,75); border-radius: 5px; }
QCheckBox::indicator:checked { background: #83cf18; border-color: #b8fa63; }
QScrollArea { background: transparent; border: 0; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: rgba(0,0,0,30); }
QScrollBar::handle:vertical { background: rgba(255,255,255,55); }
QMenuBar { background: rgba(10, 17, 15, 218); color: #e3e8e4; }
QMenu { background: rgba(18, 27, 24, 248); border: 1px solid rgba(255,255,255,55); }
QMenuBar::item:selected, QMenu::item:selected { background: rgba(118,185,0,55); color: white; }
QToolTip { background: rgba(24, 34, 31, 245); color: white; border: 1px solid rgba(255,255,255,70); border-radius: 6px; padding: 6px; }
"""


GLASS_STYLE += r"""
QWidget#rail {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(15,24,20,62), stop:1 rgba(8,18,15,102));
    border-right: 1px solid rgba(235,255,244,48);
}
QGroupBox {
    background: qlineargradient(x1:0, y1:0, x2:0.3, y2:1,
        stop:0 rgba(222,245,232,27), stop:0.14 rgba(163,194,179,18),
        stop:1 rgba(80,112,99,22));
    border-top: 1px solid rgba(237,255,246,100);
    border-left: 1px solid rgba(237,255,246,65);
    border-bottom: 1px solid rgba(237,255,246,45);
    border-right: 1px solid rgba(237,255,246,45);
    border-radius: 16px;
    padding: 22px 18px 18px;
}
QGroupBox QComboBox, QGroupBox QLineEdit, QGroupBox QSpinBox,
QGroupBox QDoubleSpinBox, QGroupBox QPlainTextEdit {
    background: rgba(6,16,12,60);
    border-color: rgba(227,245,233,80);
}
QGroupBox QComboBox QAbstractItemView, QComboBox QAbstractItemView {
    background: #18231d;
    color: #f2f6f3;
    selection-background-color: #38532c;
}
QGroupBox QProgressBar { background: rgba(236,255,245,30); }
QPushButton#nav:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(116,233,31,50), stop:1 rgba(54,180,36,88));
    color: #efffe5;
    border-left: 4px solid #9eed29;
}
QPushButton#primary, QPushButton#transport {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #abf230, stop:1 #8bdc16);
    color: #101b06;
    border-color: #c4ff68;
}
QPushButton#primary:disabled { background: rgba(92,125,53,80); color: #a9baa0; border-color: rgba(194,229,162,40); }
QMenuBar { background: rgba(6,16,12,42); padding-left: 10px; }
QStatusBar { background: transparent; }
QWidget#windowTitleBar { border-bottom: 1px solid rgba(233,253,243,30); }
"""


def normalize_theme(value):
    return value if value in ("dark", "glass") else "dark"


def theme_style(value):
    return GLASS_STYLE if normalize_theme(value) == "glass" else STYLE


def _set_dwm_attribute(hwnd, attribute, value):
    """Best-effort helper; returns False on unsupported Windows builds."""
    import ctypes
    from ctypes import wintypes
    try:
        dwm = ctypes.WinDLL("dwmapi")
        dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        data = ctypes.c_int(int(value))
        result = dwm.DwmSetWindowAttribute(
            wintypes.HWND(hwnd), ctypes.c_uint(attribute), ctypes.byref(data), ctypes.sizeof(data)
        )
        return result == 0
    except (OSError, AttributeError):
        return False


def _transparency_blocker():
    import ctypes
    from ctypes import wintypes
    import winreg
    class HIGHCONTRAST(ctypes.Structure):
        _fields_ = [("size", wintypes.UINT), ("flags", wintypes.DWORD), ("scheme", wintypes.LPWSTR)]
    contrast = HIGHCONTRAST()
    contrast.size = ctypes.sizeof(contrast)
    query = ctypes.WinDLL('user32').SystemParametersInfoW
    query.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
    query.restype = wintypes.BOOL
    if query(0x0042, contrast.size, ctypes.byref(contrast), 0) and contrast.flags & 1:
        return 'High Contrast is enabled in Windows'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
            if not bool(winreg.QueryValueEx(key, 'EnableTransparency')[0]):
                return 'Windows transparency is off — enable Transparency effects in Personalization > Colors'
    except OSError:
        pass
    return ''


def _transparency_allowed():
    return not _transparency_blocker()


def _accent_blur(hwnd, enabled):
    """Windows 10 compatibility path. ACCENT_POLICY is undocumented; failure is safe.

    Use blur (3), not acrylic (4): the latter can stall dragging on Windows 10.
    Windows 11 22H2+ uses the documented system-backdrop API first.
    """
    import ctypes as C
    from ctypes import wintypes as W
    class ACCENT_POLICY(C.Structure):
        _fields_ = [('state', C.c_int), ('flags', C.c_int), ('color', W.DWORD), ('animation', C.c_int)]
    class ATTRIBUTE(C.Structure):
        _fields_ = [('attribute', C.c_int), ('data', C.c_void_p), ('size', C.c_size_t)]
    try:
        function = C.WinDLL('user32').SetWindowCompositionAttribute
        function.argtypes = [W.HWND, C.POINTER(ATTRIBUTE)]
        function.restype = W.BOOL
        policy = ACCENT_POLICY(3 if enabled else 0, 0, 0, 0)
        data = ATTRIBUTE(19, C.cast(C.pointer(policy), C.c_void_p), C.sizeof(policy))
        return bool(function(W.HWND(hwnd), C.byref(data)))
    except (OSError, AttributeError):
        return False


def _extend_frame(hwnd, enabled):
    import ctypes as C
    from ctypes import wintypes as W
    class MARGINS(C.Structure):
        _fields_ = [('left', C.c_int), ('right', C.c_int), ('top', C.c_int), ('bottom', C.c_int)]
    try:
        function = C.WinDLL('dwmapi').DwmExtendFrameIntoClientArea
        function.argtypes = [W.HWND, C.POINTER(MARGINS)]
        function.restype = C.c_long
        margins = MARGINS(*((-1 if enabled else 0),)*4)
        return function(W.HWND(hwnd), C.byref(margins)) == 0
    except (OSError, AttributeError):
        return False


def configure_backdrop(hwnd, glass, allowed, build):
    """Version-gated native setup; injectable functions keep failure paths testable.

    Windows 10 blur is deliberately used instead of its acrylic accent state,
    which can block the native move/resize loop. No screen-copy fallback or
    wallpaper imitation is used. APIs receive only an already-visible HWND.
    """
    _set_dwm_attribute(hwnd, 20, 1)  # Immersive dark mode
    if build >= 22000:
        _set_dwm_attribute(hwnd, 33, 2)  # Native corner rounding, when supported
    if not glass or not allowed:
        _accent_blur(hwnd, False)
        if build >= 22621:
            _set_dwm_attribute(hwnd, 38, 1)
        _extend_frame(hwnd, False)
        return False, ('Classic dark' if not glass else 'Opaque — Windows transparency is off or High Contrast is enabled')
    if build >= 22621:
        _accent_blur(hwnd, False)
        if _set_dwm_attribute(hwnd, 38, 3):
            if _extend_frame(hwnd, True):
                return True, 'Native desktop acrylic — Windows 11'
            _set_dwm_attribute(hwnd, 38, 1)
    _extend_frame(hwnd, False)
    if _accent_blur(hwnd, True):
        return True, 'Native frosted blur — Windows compatibility mode'
    return False, 'Opaque fallback — Windows could not enable a native backdrop'


def apply_native_backdrop(window, value):
    import os
    import sys
    if not getattr(window, '_native_backdrop_allowed', False):
        window.setProperty('backdropMode', 'Classic window — save Glass and restart to enable translucency')
        return False
    handle = window.windowHandle()
    if handle is None or not window.isVisible():
        return False  # Never create an HWND to apply an effect.
    if os.name != 'nt':
        window.setProperty('backdropMode', 'Opaque fallback — native glass requires Windows')
        return False
    blocker = _transparency_blocker()
    enabled, status = configure_backdrop(int(handle.winId()), normalize_theme(value) == 'glass',
                                         not blocker, sys.getwindowsversion().build)
    if blocker and normalize_theme(value) == 'glass':
        status = 'Opaque — ' + blocker
    window.setProperty('backdropMode', status)
    return enabled


CHROME_STYLE = """
QGroupBox#captureCard { margin-top: 0; padding: 16px; }
QLabel#cardTitle { font-size: 12pt; font-weight: 650; }
QComboBox { min-height: 24px; }

QWidget#windowChrome, QWidget#windowTitleBar, QWidget#resizeHandle { background: transparent; }
QLabel#windowCaption { color: #ccd3cd; font-size: 9pt; background: transparent; }
QPushButton#windowControl, QPushButton#windowClose { background: transparent; border: 0; padding: 0; font-size: 14pt; color: #d8e0da; border-radius: 6px; }
QPushButton#windowControl:hover { background: rgba(255,255,255,24); }
QPushButton#windowClose:hover { background: #9c3940; color: white; }
QPushButton#windowControl:focus, QPushButton#windowClose:focus { border: 1px solid #b8cdab; }
QAbstractItemView { outline: 0; }
QListWidget::item:selected { background: rgba(118,185,0,28); border: 1px solid #76b900; }
QCheckBox { outline: 0; }
QCheckBox:focus { outline: 0; }
QCheckBox::indicator:focus { border: 1px solid #c6eaa5; }
QTableWidget::item:focus { outline: 0; }
"""


def apply_theme(window, value, extra_qss=""):
    value = normalize_theme(value)
    window._theme = value
    surface = 'transparent' if getattr(window, '_native_backdrop_allowed', False) else '#101010'
    window.setStyleSheet(theme_style(value) + extra_qss + CHROME_STYLE +
                        '\nQMainWindow, QWidget#shell { background: ' + surface + '; }')
    if hasattr(window, 'schedule_backdrop'):
        window.schedule_backdrop()
    window.update()
    return value
