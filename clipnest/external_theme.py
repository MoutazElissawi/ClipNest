"""Versioned, data-only external themes. No QSS, executable code or asset URLs.
Version 1 holds colors. Version 2 may also name a font file kept beside the theme and one of the built-in layouts."""
from __future__ import annotations
import json
import re
from pathlib import Path

LAYOUTS = ('classic', 'dial')
FONT_SUFFIXES = ('.ttf', '.otf')
MAX_FONT_BYTES = 2 * 1024 * 1024

DEFAULT_COLORS = {
    'background': '#101010', 'surface': '#181818', 'raised': '#272727',
    'border': '#3b3b3b', 'text': '#eeeeee', 'muted': '#aaaaaa',
    'accent': '#76b900', 'accent_hover': '#8ed000', 'accent_text': '#101500',
    'selection': '#253018', 'danger': '#a92b35', 'danger_hover': '#c23642',
}
# Existing component colors map to semantic roles. Glass alpha is preserved.
ALIASES = {
    'background': ['#101010', '#111111', '#121212'],
    'surface': ['#181818', '#191919', '#1a1a1a', '#1c1c1c', '#171717', '#161616'],
    'raised': ['#292929', '#323232', '#313131', '#272727', '#242424', '#252525', '#282828', '#2e2e2e', '#303030', '#262626', '#222222'],
    'border': ['#3b3b3b', '#393939', '#353535', '#363636', '#444444', '#414141', '#343434', '#404040'],
    'text': ['#eeeeee', '#f2f2f2', '#f4f4f4', '#e7e7e7', '#f4f6f4', '#f1f4f1', '#f7f8f6', '#f8f9f7', '#eef3ef', '#eef2ee', '#f3f6f3', '#f2f6f3', '#ccd3cd', '#d8e0da', '#e3e8e4'],
    'muted': ['#aaaaaa', '#999999', '#969696', '#a0a0a0', '#bbbbbb', '#b8b8b8', '#b0b0b0'],
    'accent': ['#76b900', '#9cf236', '#83cf18', '#9eed29', '#8bdc16', '#a4d65e', '#91f128', '#c7ff79', '#c8ff75'],
    'accent_hover': ['#8ed000', '#abf230', '#8bc900', '#a6dc4c'],
    'accent_text': ['#101500', '#102000', '#101b06', '#152000'],
    'selection': ['#253018', '#38532c', '#29351b', '#354822'],
    'danger': ['#a92b35', '#9c3940'], 'danger_hover': ['#c23642'],
}
_active = None
_aliases = {}  # built-in hex color -> the active palette's color for its role
_font_family = None  # family of the active theme's font, once Qt has loaded it
_loaded_fonts = {}  # font file -> family, so reloading a theme does not add the font again


def load_palette(path):
    if not isinstance(path, (str, Path)):
        raise ValueError("Theme path must be a filename.")
    source = Path(path)
    if source.stat().st_size > 65536:
        raise ValueError('Theme files must be smaller than 64 KB.')
    try:
        raw = json.loads(source.read_text(encoding='utf-8-sig'))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f'Invalid theme JSON: {exc}') from exc
    version = raw.get('schema_version') if isinstance(raw, dict) else None
    if type(version) is not int or version not in (1, 2):
        raise ValueError('Unsupported theme schema_version; expected 1 or 2.')
    allowed = {'schema_version', 'name', 'colors'} | ({'font', 'layout'} if version == 2 else set())
    if set(raw)-allowed:
        raise ValueError('Theme must contain only ' + ', '.join(sorted(allowed)) + '.')
    name = raw.get('name')
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        raise ValueError('Theme name must contain 1–80 characters.')
    colors = raw.get('colors')
    if not isinstance(colors, dict) or not colors or set(colors)-DEFAULT_COLORS.keys():
        raise ValueError('Theme colors must use the documented palette keys.')
    for key, value in colors.items():
        if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
            raise ValueError(f'{key} must be a six-digit hex color, such as #76b900.')
    palette = dict(schema_version=version, name=name.strip(), colors=dict(DEFAULT_COLORS, **colors))
    if 'font' in raw:
        font = raw['font']
        # A plain file name, so a theme can only use a font shipped in its own folder.
        if not isinstance(font, str) or Path(font).name != font or Path(font).suffix.lower() not in FONT_SUFFIXES:
            raise ValueError('font must be the name of a .ttf or .otf file in the theme folder, such as Sora.ttf.')
        file = source.parent/font
        if not file.is_file():
            raise ValueError(f'The theme font {font} is missing from {source.parent}.')
        if file.stat().st_size > MAX_FONT_BYTES:
            raise ValueError('Theme fonts must be smaller than 2 MB.')
        palette['font'] = font
    if 'layout' in raw:
        if raw['layout'] not in LAYOUTS:
            raise ValueError('layout must be one of: ' + ', '.join(LAYOUTS) + '.')
        palette['layout'] = raw['layout']
    return palette


def register_font(file):
    """Load a font file into Qt and return its family, or None when Qt cannot read it."""
    file = str(Path(file).resolve())
    if file not in _loaded_fonts:
        from PySide6.QtGui import QFontDatabase
        font_id = QFontDatabase.addApplicationFont(file)
        families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
        if not families:
            raise ValueError(f'{Path(file).name} is not a font Qt can read.')
        _loaded_fonts[file] = families[0]
    return _loaded_fonts[file]


def set_palette(path):
    """Validate before replacing the active palette. Failure leaves it untouched."""
    global _active, _aliases, _font_family
    palette = load_palette(path) if path else None
    family = register_font(Path(path).parent/palette['font']) if palette and palette.get('font') else None
    _active, _font_family = palette, family
    _aliases = {color: palette['colors'][role] for role, values in ALIASES.items() for color in values} if palette else {}
    return palette


def active_palette():
    return _active


def active_layout():
    return (_active or {}).get('layout', 'classic')


def active_font():
    return _font_family


def palette_style(qss):
    if _active is None:
        return qss
    colors = _active['colors']
    if _font_family:
        qss = qss.replace("font-family: 'Segoe UI'", f"font-family: '{_font_family}'")
    def color(match):
        token = match.group().lower()
        if len(token) == 4:
            token = '#' + ''.join(c*2 for c in token[1:])
        return _aliases.get(token, match.group())
    qss = re.sub(r'#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b', color, qss)
    def rgba(match):
        r, g, b, alpha = map(int, match.groups())
        role = 'accent' if (r,g,b) in ((118,185,0),(147,241,40),(91,211,43),(116,233,31),(54,180,36)) else None
        if role:
            c = colors[role]
            return f'rgba({int(c[1:3],16)},{int(c[3:5],16)},{int(c[5:7],16)},{alpha})'
        return match.group()
    return re.sub(r'rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', rgba, qss)


def apply_inline_palettes(window):
    from PySide6.QtWidgets import QWidget
    for widget in window.findChildren(QWidget):
        # Secondary windows own their root stylesheet.
        if widget.isWindow():
            continue
        current = widget.styleSheet()
        last = getattr(widget, '_palette_last_qss', None)
        if last is None and not current:
            continue  # most widgets use only their window's stylesheet
        if last is None or current != last:
            widget._palette_base_qss = current
        base = getattr(widget, '_palette_base_qss', current)
        changed = palette_style(base)
        if changed != current:
            widget.setStyleSheet(changed)
        widget._palette_last_qss = changed
