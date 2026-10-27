"""Versioned, data-only external palettes. No QSS, executable code or asset URLs."""
from __future__ import annotations
import json
import re
from pathlib import Path

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
_active_path = ''


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
    if not isinstance(raw, dict) or set(raw)-{'schema_version', 'name', 'colors'}:
        raise ValueError('Theme must contain only schema_version, name and colors.')
    if type(raw.get('schema_version')) is not int or raw['schema_version'] != 1:
        raise ValueError('Unsupported theme schema_version; expected 1.')
    name = raw.get('name')
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        raise ValueError('Theme name must contain 1–80 characters.')
    colors = raw.get('colors')
    if not isinstance(colors, dict) or not colors or set(colors)-DEFAULT_COLORS.keys():
        raise ValueError('Theme colors must use the documented palette keys.')
    for key, value in colors.items():
        if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
            raise ValueError(f'{key} must be a six-digit hex color, such as #76b900.')
    return dict(schema_version=1, name=name.strip(), colors=dict(DEFAULT_COLORS, **colors))


def set_palette(path):
    """Validate before replacing the active palette. Failure leaves it untouched."""
    global _active, _active_path
    palette = load_palette(path) if path else None
    _active, _active_path = palette, str(path or '')
    return palette


def active_palette():
    return _active


def palette_style(qss):
    if _active is None:
        return qss
    colors = _active['colors']
    aliases = {color: colors[role] for role, values in ALIASES.items() for color in values}
    def color(match):
        token = match.group().lower()
        if len(token) == 4:
            token = '#' + ''.join(c*2 for c in token[1:])
        return aliases.get(token, match.group())
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
        if last is None or current != last:
            widget._palette_base_qss = current
        base = getattr(widget, '_palette_base_qss', current)
        changed = palette_style(base)
        if changed != current:
            widget.setStyleSheet(changed)
        widget._palette_last_qss = changed
