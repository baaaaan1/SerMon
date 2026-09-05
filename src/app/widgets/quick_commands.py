"""Quick-commands panel: one-click preset transmit lines.

The widget is a thin Qt layer over the Qt-free :class:`QuickCommandsModel`.  It
emits :attr:`send_requested` (str) when the user activates a preset (double-click
or Enter), and allows the list to be edited in place / added / removed.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..models.quick_commands import QuickCommandsModel


class QuickCommands(QWidget):
    """An editable list of preset send-lines."""

    send_requested = Signal(str)

    def __init__(
        self,
        model: QuickCommandsModel | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("quickCommands")
        self._model = model or QuickCommandsModel()

        self._list = QListWidget(self)
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._list.setToolTip("Double-click a line (or press Enter) to send it.")

        self._add_btn = QPushButton("Add", self)
        self._add_btn.setToolTip("Add a new quick command.")
        self._remove_btn = QPushButton("Remove", self)
        self._remove_btn.setToolTip("Remove the selected quick command.")

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(6)
        buttons.addWidget(self._add_btn)
        buttons.addWidget(self._remove_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        title = QLabel("Quick Commands", self)
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        layout.addWidget(self._list, 1)
        layout.addLayout(buttons)

        self._list.itemActivated.connect(self._on_activated)
        self._list.itemChanged.connect(self._on_edited)
        self._add_btn.clicked.connect(self._on_add)
        self._remove_btn.clicked.connect(self._on_remove)

        self._reload()

    # -- Introspection --------------------------------------------------------

    @property
    def model(self) -> QuickCommandsModel:
        """The underlying (Qt-free) data model."""
        return self._model

    @property
    def list_widget(self) -> QListWidget:
        """The list widget holding the visible items."""
        return self._list

    # -- Internal helpers -----------------------------------------------------

    def _reload(self) -> None:
        """Re-populate the list from the model."""
        self._list.blockSignals(True)
        try:
            self._list.clear()
            for command in self._model.commands:
                item = QListWidgetItem(command)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                self._list.addItem(item)
        finally:
            self._list.blockSignals(False)

    def _on_activated(self, item: QListWidgetItem) -> None:
        text = item.text().strip()
        if text:
            self.send_requested.emit(text)

    def _on_edited(self, item: QListWidgetItem) -> None:
        self._model.set_command(self._list.row(item), item.text())

    def _on_add(self) -> None:
        self._model.add("")
        self._reload()
        row = self._list.count() - 1
        if row >= 0:
            self._list.setCurrentRow(row)
            self._list.editItem(self._list.item(row))

    def _on_remove(self) -> None:
        row = self._list.currentRow()
        if 0 <= row < self._list.count():
            self._model.remove(row)
            self._reload()
