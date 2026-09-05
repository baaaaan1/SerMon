"""PySide6 UI layer.

This is the only layer that is allowed to import PySide6.  It depends on the
Qt-free :mod:`serial` engine through :class:`~app.bridge.SerialBridge`, which
adapts engine callbacks into Qt signals.  Widgets never touch pyserial directly.
"""
