"""Reusable sidebar panel that gathers the connection settings.

The panel is a pure *view*: it exposes its widgets as public attributes and
leaves connect/refresh/persistence logic to the window.  The advanced line
settings (data bits, parity, stop bits, flow control, DTR/RTS) mirror the
values supported by :mod:`serial_engine.config`.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from serial_engine.config import (
    SUPPORTED_BAUDRATES,
    SUPPORTED_DATA_BITS,
    SUPPORTED_FLOW_CONTROL,
    SUPPORTED_PARITIES,
    SUPPORTED_STOP_BITS,
)

#: 1.5 stop bits is only valid with 5 data bits, which the UI never offers.
_STOP_BITS_OFFERED = tuple(v for v in SUPPORTED_STOP_BITS if v != 1.5)


class ConnectionPanel(QWidget):
    """Connection configuration panel (port, baud, line settings, connect)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("connectionPanel")

        # -- Port selection ---------------------------------------------------
        self.port_combo = QComboBox(self)
        self.port_combo.setMinimumContentsLength(20)
        self.port_combo.setObjectName("portCombo")
        self.port_combo.setToolTip("Target serial port (e.g. COM3 or /dev/ttyUSB0).")

        self.refresh_btn = QPushButton("⟳", self)
        self.refresh_btn.setFixedWidth(34)
        self.refresh_btn.setObjectName("refreshBtn")
        self.refresh_btn.setToolTip("Refresh the list of available ports (F5).")

        port_row = QHBoxLayout()
        port_row.setContentsMargins(0, 0, 0, 0)
        port_row.setSpacing(6)
        port_row.addWidget(self.port_combo, 1)
        port_row.addWidget(self.refresh_btn)

        # -- Baudrate ---------------------------------------------------------
        self.baud_combo = QComboBox(self)
        self.baud_combo.setEditable(True)
        self.baud_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.baud_combo.addItems([str(b) for b in SUPPORTED_BAUDRATES])
        self.baud_combo.setCurrentText("9600")
        self.baud_combo.setToolTip("Baud rate of the connection (bits per second).")

        # -- Advanced line settings ------------------------------------------
        self.data_bits_combo = QComboBox(self)
        for value in SUPPORTED_DATA_BITS:
            self.data_bits_combo.addItem(f"{value} bits", value)
        self.data_bits_combo.setToolTip("Data bits per character (usually 8).")

        self.parity_combo = QComboBox(self)
        self.parity_combo.addItems(list(SUPPORTED_PARITIES))
        self.parity_combo.setToolTip("Parity checking (None is typical).")

        self.stop_bits_combo = QComboBox(self)
        for value in _STOP_BITS_OFFERED:
            self.stop_bits_combo.addItem(f"{value:g} stop", value)
        self.stop_bits_combo.setToolTip("Number of stop bits after each character.")

        self.flow_combo = QComboBox(self)
        self.flow_combo.addItems(list(SUPPORTED_FLOW_CONTROL))
        self.flow_combo.setToolTip("Hardware/software flow control.")

        config_group = QGroupBox("Configuration", self)
        config_group.setObjectName("configGroup")
        cfg_form = QFormLayout(config_group)
        cfg_form.setContentsMargins(8, 8, 8, 8)
        cfg_form.setSpacing(6)
        cfg_form.addRow("Data bits:", self.data_bits_combo)
        cfg_form.addRow("Parity:", self.parity_combo)
        cfg_form.addRow("Stop bits:", self.stop_bits_combo)
        cfg_form.addRow("Flow:", self.flow_combo)

        # -- Line-control toggles --------------------------------------------
        self.dtr_check = QCheckBox("DTR", self)
        self.dtr_check.setChecked(True)
        self.dtr_check.setToolTip("Toggle the DTR line; applies live while connected.")
        self.rts_check = QCheckBox("RTS", self)
        self.rts_check.setChecked(True)
        self.rts_check.setToolTip("Toggle the RTS line; applies live while connected.")

        line_row = QHBoxLayout()
        line_row.setContentsMargins(0, 0, 0, 0)
        line_row.addWidget(self.dtr_check)
        line_row.addWidget(self.rts_check)
        line_row.addStretch(1)

        # -- Auto-reconnect ---------------------------------------------------
        self.reconnect_check = QCheckBox("Auto reconnect", self)
        self.reconnect_check.setChecked(True)
        self.reconnect_check.setToolTip(
            "Automatically reconnect when the device is unplugged or disappears."
        )

        self.reconnect_interval_spin = QDoubleSpinBox(self)
        self.reconnect_interval_spin.setRange(0.5, 60.0)
        self.reconnect_interval_spin.setSingleStep(0.5)
        self.reconnect_interval_spin.setDecimals(1)
        self.reconnect_interval_spin.setValue(1.0)
        self.reconnect_interval_spin.setSuffix(" s")
        self.reconnect_interval_spin.setToolTip(
            "How often to retry the connection while waiting for the device."
        )

        reconnect_row = QHBoxLayout()
        reconnect_row.setContentsMargins(0, 0, 0, 0)
        reconnect_row.setSpacing(6)
        reconnect_row.addWidget(self.reconnect_check)
        reconnect_row.addStretch(1)
        reconnect_row.addWidget(QLabel("Retry:", self))
        reconnect_row.addWidget(self.reconnect_interval_spin)

        # -- Connect button ---------------------------------------------------
        self.connect_btn = QPushButton("Connect", self)
        self.connect_btn.setObjectName("connectBtn")
        self.connect_btn.setToolTip("Open the connection (Ctrl+Enter).")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = QLabel("COM Port", self)
        label.setObjectName("sectionTitle")
        layout.addWidget(label)
        layout.addLayout(port_row)
        label = QLabel("Baudrate", self)
        label.setObjectName("sectionTitle")
        layout.addWidget(label)
        layout.addWidget(self.baud_combo)
        layout.addWidget(config_group)
        layout.addLayout(line_row)
        layout.addLayout(reconnect_row)
        layout.addWidget(self.connect_btn)
