"""Offline Lucide icons from https://icon-sets.iconify.design/lucide/.

SVG geometry: https://api.iconify.design/lucide.json
Copyright Lucide contributors (ISC) and Cole Bemis (MIT).
The bundled notices are in assets/lucide-LICENSE.txt.
"""

from functools import lru_cache

from PySide6.QtCore import QByteArray
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from theme import PALETTE


_BODIES = {
    "plug": '<path d="M12 22v-5m3-9V2m2 6a1 1 0 0 1 1 1v4a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V9a1 1 0 0 1 1-1zM9 8V2"/>',
    "unplug": '<path d="m19 5l3-3M2 22l3-3m1.3 1.3a2.4 2.4 0 0 0 3.4 0L12 18l-6-6l-2.3 2.3a2.4 2.4 0 0 0 0 3.4Zm1.2-6.8L10 11m.5 5.5L13 14m-1-8l6 6l2.3-2.3a2.4 2.4 0 0 0 0-3.4l-2.6-2.6a2.4 2.4 0 0 0-3.4 0Z"/>',
    "refresh-cw": '<path d="M3 12a9 9 0 0 1 9-9a9.75 9.75 0 0 1 6.74 2.74L21 8M21 3v5h-5m5 4a9 9 0 0 1-9 9a9.75 9.75 0 0 1-6.74-2.74L3 16M8 16H3v5"/>',
    "send": '<path d="M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11zm7.318-19.539l-10.94 10.939"/>',
    "trash": '<path d="M10 11v6m4-6v6m5-11v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
    "copy": '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    "download": '<path d="M12 15V3m9 12v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4m4-5l5 5l5-5"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "cable": '<path d="M17 19a1 1 0 0 1-1-1v-2a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2a1 1 0 0 1-1 1zm0 2v-2M19 14V6.5a1 1 0 0 0-7 0v11a1 1 0 0 1-7 0V10m16 11v-2M3 5V3m1 7a2 2 0 0 1-2-2V6a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2a2 2 0 0 1-2 2zm3-5V3"/>',
    "eraser": '<path d="M21 21H8a2 2 0 0 1-1.42-.587l-3.994-3.999a2 2 0 0 1 0-2.828l10-10a2 2 0 0 1 2.829 0l5.999 6a2 2 0 0 1 0 2.828L12.834 21m-7.752-9.91l8.828 8.828"/>',
    "arrow-down-to-line": '<path d="M12 17V3m-6 8l6 6l6-6m1 10H5"/>',
    "terminal": '<path d="M12 19h8M4 17l6-6l-6-6"/>',
    "keyboard": '<path d="M10 8h.01M12 12h.01M14 8h.01M16 12h.01M18 8h.01M6 8h.01M7 16h10m-9-4h.01"/><rect width="20" height="16" x="2" y="4" rx="2"/>',
}


@lru_cache(maxsize=32)
def icon(name: str) -> QIcon:
    """Render bundled SVGs at multiple sizes, with active/disabled variants."""
    result = QIcon()
    for color, mode, states in (
        (PALETTE["text"], QIcon.Normal, (QIcon.Off,)),
        (PALETTE["accent"], QIcon.Normal, (QIcon.On,)),
        (PALETTE["text_muted"], QIcon.Disabled, (QIcon.Off, QIcon.On)),
    ):
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="%s" stroke-width="2" stroke-linecap="round" '
            'stroke-linejoin="round">%s</svg>' % (color, _BODIES[name])
        )
        renderer = QSvgRenderer(QByteArray(svg.encode("ascii")))
        for size in (16, 20, 24, 32, 48, 64):
            pixmap = QPixmap(size, size)
            pixmap.fill("transparent")
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            for state in states:
                result.addPixmap(pixmap, mode, state)
    return result
