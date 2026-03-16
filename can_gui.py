"""
CAN Communication GUI – VN1640A (Vector XL backend)
=====================================================
Hardware : Vector VN1640A
  CAN1   : Hardware channel 3  →  DUT
  CAN2   : Hardware channel 4  →  Power Supply 1 & 2

Dependencies (install once):
    pip install python-can cantools PyQt5 pyqtgraph pandas

Usage:
    python can_gui.py
"""

# ─────────────────────────────────────────────────────────────────────────────
# USER-EDITABLE PARAMETERS
# ─────────────────────────────────────────────────────────────────────────────
DBC_DUT_PATH   = "dut.dbc"     # DBC for CAN1 / DUT
DBC_PS_PATH    = "ps.dbc"      # DBC for CAN2 / Power Supplies

CAN1_APP_NAME  = "CANalyzer"   # Vector app-name for channel 3
CAN2_APP_NAME  = "CANalyzer"   # Vector app-name for channel 4
CAN1_HW_CH     = 3             # VN1640A physical channel for DUT
CAN2_HW_CH     = 4             # VN1640A physical channel for PS
BITRATE        = 500_000

# Diagnostic response display duration (seconds)
DIAG_DISPLAY_DURATION = 1.0

# ─── DUT signal configuration ────────────────────────────────────────────────
# Signals to WRITE to DUT  (name in DBC, display label, unit, min, max, default)
DUT_WRITE_SIGNALS = [
    # (dbc_signal_name,       label,               unit,  min,   max,  default, is_diag)
    ("DUT_TargetVoltage",     "Target Voltage",    "V",   0,     80,   0.0,    False),
    ("DUT_TargetCurrent",     "Target Current",    "A",  -100,  100,   0.0,    False),
    ("DUT_ControlMode",       "Control Mode",      "",    0,      3,   0,      False),
    ("DUT_EnableOutput",      "Enable Output",     "",    0,      1,   0,      False),
    ("DUT_FaultReset",        "Fault Reset",       "",    0,      1,   0,      False),
    ("DUT_OperatingMode",     "Operating Mode",    "",    0,      7,   0,      False),
    ("DUT_DiagRequest",       "Diag Request",      "",    0,   0xFF,   0x00,   True ),  # ← sent via button
]

# Signals to READ from DUT  (dbc_signal_name, label, unit, min, max, is_voltage_current)
DUT_READ_SIGNALS = [
    ("DUT_OutputVoltage",   "Output Voltage",   "V",     0,    80,   "voltage"),
    ("DUT_OutputCurrent",   "Output Current",   "A",  -100,  100,   "current"),
    ("DUT_BusVoltage",      "Bus Voltage",      "V",     0,    80,   "voltage"),
    ("DUT_InductorCurrent", "Inductor Current", "A",  -100,  100,   "current"),
    ("DUT_Temperature",     "Temperature",      "°C",    0,   150,   None),
    ("DUT_StatusFlags",     "Status Flags",     "",      0,  0xFF,   None),
    ("DUT_DiagResponse",    "Diag Response",    "",      0,  0xFF,   "diag"),  # ← full-frame display
]

# ─── Power Supply signal configuration ───────────────────────────────────────
# 13 write signals per PS  (name suffix changes per PS based on message ID in DBC)
PS_WRITE_SIGNALS = [
    # (suffix,              label,                  unit,  min,    max,  default, widget)
    # widget: "spinbox" | "switch" | "onoff"
    ("RemoteAccess",        "Remote Access",        "",    1,      2,    2,      "switch"),   # ON→1 OFF→2
    ("OutputEnable",        "Output Enable",        "",    0,      1,    0,      "onoff"),    # ON→1 OFF→0
    ("VoltageSetpoint",     "Voltage Setpoint",     "V",   0,    100,   0.0,    "spinbox"),
    ("CurrentLimit",        "Current Limit",        "A",   0,     50,   0.0,    "spinbox"),
    ("OVPThreshold",        "OVP Threshold",        "V",   0,    120,   110.0,  "spinbox"),
    ("OCP Threshold",       "OCP Threshold",        "A",   0,     60,   55.0,   "spinbox"),
    ("FoldbackMode",        "Foldback Mode",        "",    0,      3,   0,      "spinbox"),
    ("RampRate",            "Ramp Rate",            "V/s", 0,    999,   10.0,   "spinbox"),
    ("SlewRate",            "Slew Rate",            "A/s", 0,    999,   10.0,   "spinbox"),
    ("ProtectionDelay",     "Protection Delay",     "ms",  0,    999,   100.0,  "spinbox"),
    ("ParallelMode",        "Parallel Mode",        "",    0,      1,   0,      "spinbox"),
    ("FanControl",          "Fan Control",          "",    0,      1,   0,      "spinbox"),
    ("ConfigSave",          "Config Save",          "",    0,      1,   0,      "spinbox"),
]

# 3 read signals per PS
PS_READ_SIGNALS = [
    ("MeasuredVoltage",  "Measured Voltage", "V",   0,   100),
    ("MeasuredCurrent",  "Measured Current", "A",   0,    50),
    ("StatusWord",       "Status Word",      "",    0, 0xFFFF),
]

# PS1 and PS2 DBC message name prefixes (adapt to your DBC)
PS1_PREFIX = "PS1_"
PS2_PREFIX = "PS2_"

# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS
# ─────────────────────────────────────────────────────────────────────────────
import sys, os, time, threading, logging, csv, math, datetime
from collections import defaultdict

import can
import cantools

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget,
    QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QPushButton, QDoubleSpinBox, QSpinBox, QLineEdit,
    QFileDialog, QCheckBox, QComboBox, QScrollArea, QFrame,
    QSizePolicy, QSplitter, QTextEdit, QProgressBar,
    QMessageBox, QSlider, QDial
)
from PyQt5.QtCore import (
    Qt, QTimer, pyqtSignal, QObject, QThread, QMutex,
    QPropertyAnimation, QEasingCurve
)
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QFontMetrics,
    QPainterPath, QLinearGradient, QRadialGradient, QPalette
)

# ─────────────────────────────────────────────────────────────────────────────
# DARK THEME STYLESHEET
# ─────────────────────────────────────────────────────────────────────────────
DARK_STYLE = """
QMainWindow, QWidget {
    background-color: #0d1117;
    color: #e6edf3;
    font-family: "Segoe UI", "Ubuntu", sans-serif;
    font-size: 13px;
}
QTabWidget::pane {
    border: 1px solid #30363d;
    border-radius: 6px;
    background: #161b22;
}
QTabBar::tab {
    background: #21262d;
    color: #8b949e;
    border: 1px solid #30363d;
    padding: 8px 20px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #161b22;
    color: #58a6ff;
    border-bottom-color: #161b22;
}
QTabBar::tab:hover { background: #30363d; color: #e6edf3; }
QGroupBox {
    border: 1px solid #30363d;
    border-radius: 8px;
    margin-top: 14px;
    padding: 10px 8px 8px 8px;
    font-weight: 600;
    color: #58a6ff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #58a6ff;
}
QPushButton {
    background-color: #21262d;
    color: #e6edf3;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: 500;
}
QPushButton:hover { background-color: #30363d; border-color: #58a6ff; }
QPushButton:pressed { background-color: #1f6feb; border-color: #1f6feb; }
QPushButton:disabled { color: #484f58; border-color: #21262d; }
QPushButton#btnPrimary {
    background-color: #1f6feb;
    border-color: #1f6feb;
    color: white;
    font-weight: 600;
}
QPushButton#btnPrimary:hover { background-color: #388bfd; }
QPushButton#btnDanger {
    background-color: #da3633;
    border-color: #da3633;
    color: white;
}
QPushButton#btnDanger:hover { background-color: #f85149; }
QPushButton#btnSuccess {
    background-color: #238636;
    border-color: #238636;
    color: white;
}
QPushButton#btnSuccess:hover { background-color: #2ea043; }
QDoubleSpinBox, QSpinBox, QLineEdit, QComboBox {
    background-color: #21262d;
    color: #e6edf3;
    border: 1px solid #30363d;
    border-radius: 5px;
    padding: 4px 8px;
    selection-background-color: #1f6feb;
}
QDoubleSpinBox:focus, QSpinBox:focus, QLineEdit:focus, QComboBox:focus {
    border-color: #58a6ff;
}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button, QSpinBox::down-button {
    background: #30363d;
    border: none;
    width: 16px;
}
QScrollArea { border: none; }
QScrollBar:vertical {
    background: #161b22;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #30363d;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #58a6ff; }
QTextEdit {
    background-color: #0d1117;
    color: #7ee787;
    border: 1px solid #30363d;
    border-radius: 6px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
}
QCheckBox { spacing: 6px; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 1px solid #30363d;
    border-radius: 3px;
    background: #21262d;
}
QCheckBox::indicator:checked {
    background: #1f6feb;
    border-color: #1f6feb;
    image: none;
}
QLabel#value_label {
    color: #7ee787;
    font-size: 15px;
    font-weight: 700;
}
QLabel#unit_label {
    color: #8b949e;
    font-size: 11px;
}
QFrame#divider {
    background-color: #30363d;
    max-height: 1px;
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# ANALOG METER WIDGET
# ─────────────────────────────────────────────────────────────────────────────
class AnalogMeter(QWidget):
    """Circular analog gauge with coloured arc and needle."""

    def __init__(self, label="", unit="", min_val=0, max_val=100,
                 meter_type="generic", parent=None):
        super().__init__(parent)
        self.label    = label
        self.unit     = unit
        self.min_val  = min_val
        self.max_val  = max_val
        self.value    = min_val
        self.meter_type = meter_type        # "voltage" | "current" | "generic"
        self.setMinimumSize(180, 180)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def setValue(self, v):
        self.value = max(self.min_val, min(self.max_val, v))
        self.update()

    # ── sweep: 225° (start 225° from 3-o'clock going clockwise) ──────────────
    def _angle(self, v):
        """Map value → painter angle (degrees, 0=3-o'clock, CW positive)."""
        ratio = (v - self.min_val) / (self.max_val - self.min_val)
        return 225 - ratio * 270          # 225° → -45°  (Qt: CW, so negate)

    def paintEvent(self, event):
        w, h   = self.width(), self.height()
        side   = min(w, h) - 10
        cx, cy = w // 2, h // 2
        r      = side // 2

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Background circle
        p.setPen(Qt.NoPen)
        grad = QRadialGradient(cx, cy, r)
        grad.setColorAt(0.0, QColor("#1c2333"))
        grad.setColorAt(1.0, QColor("#0d1117"))
        p.setBrush(grad)
        p.drawEllipse(cx - r, cy - r, side, side)

        # Outer rim
        p.setPen(QPen(QColor("#30363d"), 3))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(cx - r, cy - r, side, side)

        # Coloured arc track
        arc_rect_m = 12
        arc_r      = r - arc_rect_m
        start_deg  = 225
        span_deg   = -270          # CCW in Qt coords: negative for CW sweep

        # Background track
        p.setPen(QPen(QColor("#21262d"), 8, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(cx - arc_r, cy - arc_r, arc_r * 2, arc_r * 2,
                  start_deg * 16, span_deg * 16)

        # Value arc
        ratio      = (self.value - self.min_val) / (self.max_val - self.min_val)
        span_val   = span_deg * ratio
        if self.meter_type == "voltage":
            arc_color = QColor("#58a6ff")
        elif self.meter_type == "current":
            # Positive → green, negative → orange
            arc_color = QColor("#2ea043") if self.value >= 0 else QColor("#d29922")
        else:
            arc_color = QColor("#a371f7")

        p.setPen(QPen(arc_color, 8, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(cx - arc_r, cy - arc_r, arc_r * 2, arc_r * 2,
                  start_deg * 16, int(span_val * 16))

        # Tick marks
        p.setPen(QPen(QColor("#484f58"), 1))
        for i in range(11):
            angle_deg = 225 - (i / 10) * 270
            angle_rad = math.radians(angle_deg)
            inner_r   = r - 22
            outer_r   = r - 10
            x1 = cx + inner_r * math.cos(angle_rad)
            y1 = cy - inner_r * math.sin(angle_rad)
            x2 = cx + outer_r * math.cos(angle_rad)
            y2 = cy - outer_r * math.sin(angle_rad)
            p.drawLine(int(x1), int(y1), int(x2), int(y2))

        # Needle
        angle_rad = math.radians(self._angle(self.value))
        needle_r  = r - 26
        tip_x     = cx + needle_r * math.cos(angle_rad)
        tip_y     = cy - needle_r * math.sin(angle_rad)
        base_r    = 8
        perp_rad  = angle_rad + math.pi / 2
        b1x = cx + base_r * math.cos(perp_rad)
        b1y = cy - base_r * math.sin(perp_rad)
        b2x = cx - base_r * math.cos(perp_rad)
        b2y = cy + base_r * math.sin(perp_rad)

        path = QPainterPath()
        path.moveTo(tip_x, tip_y)
        path.lineTo(b1x, b1y)
        path.lineTo(b2x, b2y)
        path.closeSubpath()

        needle_color = QColor("#f85149")
        p.setPen(Qt.NoPen)
        p.setBrush(needle_color)
        p.drawPath(path)

        # Centre cap
        p.setBrush(QColor("#e6edf3"))
        cap_r = 6
        p.drawEllipse(cx - cap_r, cy - cap_r, cap_r * 2, cap_r * 2)

        # Value text
        p.setPen(QColor("#e6edf3"))
        val_font = QFont("Segoe UI", 11, QFont.Bold)
        p.setFont(val_font)
        val_str = f"{self.value:.1f}"
        fm = QFontMetrics(val_font)
        p.drawText(cx - fm.horizontalAdvance(val_str) // 2,
                   cy + int(r * 0.45), val_str)

        # Unit
        p.setPen(QColor("#8b949e"))
        unit_font = QFont("Segoe UI", 8)
        p.setFont(unit_font)
        fm2 = QFontMetrics(unit_font)
        p.drawText(cx - fm2.horizontalAdvance(self.unit) // 2,
                   cy + int(r * 0.60), self.unit)

        # Label at bottom
        p.setPen(QColor("#58a6ff"))
        lbl_font = QFont("Segoe UI", 8, QFont.Bold)
        p.setFont(lbl_font)
        fm3 = QFontMetrics(lbl_font)
        p.drawText(cx - fm3.horizontalAdvance(self.label) // 2,
                   cy + int(r * 0.80), self.label)

# ─────────────────────────────────────────────────────────────────────────────
# LED INDICATOR
# ─────────────────────────────────────────────────────────────────────────────
class LEDIndicator(QWidget):
    def __init__(self, color_on="#2ea043", color_off="#21262d", size=14, parent=None):
        super().__init__(parent)
        self._on         = False
        self._color_on   = QColor(color_on)
        self._color_off  = QColor(color_off)
        self.setFixedSize(size, size)

    def setState(self, on: bool):
        self._on = on
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = self._color_on if self._on else self._color_off
        p.setPen(QPen(color.darker(130), 1))
        p.setBrush(color)
        p.drawEllipse(1, 1, self.width() - 2, self.height() - 2)

# ─────────────────────────────────────────────────────────────────────────────
# TOGGLE SWITCH WIDGET
# ─────────────────────────────────────────────────────────────────────────────
class ToggleSwitch(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, on_label="ON", off_label="OFF", parent=None):
        super().__init__(parent)
        self._checked   = False
        self.on_label   = on_label
        self.off_label  = off_label
        self.setFixedSize(70, 30)
        self.setCursor(Qt.PointingHandCursor)

    def isChecked(self):
        return self._checked

    def setChecked(self, v):
        self._checked = v
        self.update()

    def mousePressEvent(self, event):
        self._checked = not self._checked
        self.update()
        self.toggled.emit(self._checked)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        bg   = QColor("#238636") if self._checked else QColor("#484f58")
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(0, 0, w, h, h // 2, h // 2)
        # Thumb
        thumb_x = w - h + 2 if self._checked else 2
        p.setBrush(QColor("#e6edf3"))
        p.drawEllipse(thumb_x, 2, h - 4, h - 4)
        # Label
        p.setPen(QColor("#e6edf3"))
        p.setFont(QFont("Segoe UI", 8, QFont.Bold))
        lbl = self.on_label if self._checked else self.off_label
        p.drawText(0, 0, w, h, Qt.AlignCenter, lbl)

# ─────────────────────────────────────────────────────────────────────────────
# CAN BUS WORKER THREAD
# ─────────────────────────────────────────────────────────────────────────────
class CANWorker(QObject):
    signal_received  = pyqtSignal(str, float)   # (signal_name, value)
    frame_received   = pyqtSignal(int, bytes)    # (arb_id, data)
    connection_status = pyqtSignal(bool, str)    # (ok, message)

    def __init__(self, db_dut, db_ps, channel1=0, channel2=1):
        super().__init__()
        self.db_dut   = db_dut
        self.db_ps    = db_ps
        self.ch1      = channel1   # DUT bus
        self.ch2      = channel2   # PS bus
        self.bus1     = None
        self.bus2     = None
        self._running = False
        self._mutex   = QMutex()

    def connect_buses(self):
        errors = []
        try:
            self.bus1 = can.interface.Bus(
                bustype='vector',
                app_name=CAN1_APP_NAME,
                channel=self.ch1,
                bitrate=BITRATE
            )
        except Exception as e:
            errors.append(f"CAN1: {e}")

        try:
            self.bus2 = can.interface.Bus(
                bustype='vector',
                app_name=CAN2_APP_NAME,
                channel=self.ch2,
                bitrate=BITRATE
            )
        except Exception as e:
            errors.append(f"CAN2: {e}")

        if errors:
            self.connection_status.emit(False, " | ".join(errors))
        else:
            self.connection_status.emit(True, "Both CAN buses connected.")
        return not bool(errors)

    def run(self):
        self._running = True
        while self._running:
            for bus, db in ((self.bus1, self.db_dut), (self.bus2, self.db_ps)):
                if bus is None:
                    continue
                try:
                    msg = bus.recv(timeout=0.01)
                    if msg is None:
                        continue
                    self.frame_received.emit(msg.arbitration_id, bytes(msg.data))
                    try:
                        decoded = db.decode_message(msg.arbitration_id, msg.data)
                        for sig_name, val in decoded.items():
                            self.signal_received.emit(sig_name, float(val))
                    except Exception:
                        pass
                except Exception:
                    pass

    def send(self, bus_id, arb_id, data: bytes):
        bus = self.bus1 if bus_id == 1 else self.bus2
        if bus is None:
            return False
        try:
            msg = can.Message(arbitration_id=arb_id,
                              data=data, is_extended_id=False)
            bus.send(msg)
            return True
        except Exception as e:
            logging.error(f"CAN send error: {e}")
            return False

    def stop(self):
        self._running = False
        if self.bus1:
            try: self.bus1.shutdown()
            except: pass
        if self.bus2:
            try: self.bus2.shutdown()
            except: pass

# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL ENCODER HELPER
# ─────────────────────────────────────────────────────────────────────────────
def encode_and_get_frame(db, signal_name: str, value: float):
    """Find the message containing signal_name, encode it, return (arb_id, data)."""
    for msg in db.messages:
        for sig in msg.signals:
            if sig.name == signal_name:
                data = db.encode_message(msg.frame_id, {signal_name: value})
                return msg.frame_id, data
    return None, None

# ─────────────────────────────────────────────────────────────────────────────
# DUT PANEL
# ─────────────────────────────────────────────────────────────────────────────
class DUTPanel(QWidget):
    send_requested = pyqtSignal(int, int, bytes)   # (bus_id, arb_id, data)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db          = db
        self.diag_timer  = QTimer()
        self.diag_timer.setSingleShot(True)
        self.diag_timer.timeout.connect(self._clear_diag)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        # ── Title ──────────────────────────────────────────────────────────
        title = QLabel("DUT  –  CAN1  (Channel 3)")
        title.setStyleSheet("font-size:15px;font-weight:700;color:#58a6ff;")
        root.addWidget(title)

        divider = QFrame(); divider.setObjectName("divider")
        root.addWidget(divider)

        splitter = QSplitter(Qt.Horizontal)

        # ── LEFT: Write signals ────────────────────────────────────────────
        write_group = QGroupBox("Write Signals →  DUT")
        wg_layout   = QGridLayout(write_group)
        wg_layout.setSpacing(8)

        self.write_spinboxes = {}
        self.write_labels    = {}

        for row, (sig_name, label, unit, mn, mx, default, is_diag) in \
                enumerate(DUT_WRITE_SIGNALS):
            lbl = QLabel(f"{label}")
            lbl.setToolTip(sig_name)

            if is_diag:
                # Hex input + dedicated Send button
                edit = QLineEdit(f"0x{int(default):02X}")
                edit.setFixedWidth(90)
                self.write_spinboxes[sig_name] = edit
                btn  = QPushButton("Send Diag")
                btn.setObjectName("btnPrimary")
                btn.setFixedWidth(95)
                btn.clicked.connect(lambda _, s=sig_name: self._send_diag(s))
                wg_layout.addWidget(lbl,  row, 0)
                wg_layout.addWidget(edit, row, 1)
                wg_layout.addWidget(btn,  row, 2)
            else:
                sb = QDoubleSpinBox()
                sb.setRange(mn, mx)
                sb.setValue(default)
                sb.setSuffix(f"  {unit}" if unit else "")
                sb.setDecimals(2 if isinstance(default, float) else 0)
                sb.setFixedWidth(130)
                sb.valueChanged.connect(lambda v, s=sig_name: self._auto_send(s, v))
                self.write_spinboxes[sig_name] = sb
                wg_layout.addWidget(lbl, row, 0)
                wg_layout.addWidget(sb,  row, 1, 1, 2)

        write_group.setLayout(wg_layout)
        splitter.addWidget(write_group)

        # ── RIGHT: Read signals ────────────────────────────────────────────
        read_group = QGroupBox("Read Signals ←  DUT")
        rg_layout  = QVBoxLayout(read_group)

        # Analog meters for voltage/current
        meters_row  = QHBoxLayout()
        self.meters = {}
        for sig_name, label, unit, mn, mx, sig_type in DUT_READ_SIGNALS:
            if sig_type in ("voltage", "current"):
                meter = AnalogMeter(label, unit, mn, mx, sig_type)
                self.meters[sig_name] = meter
                meters_row.addWidget(meter)
        rg_layout.addLayout(meters_row)

        # Other read signals as value labels
        grid = QGridLayout()
        self.read_labels = {}
        non_meter = [(s, l, u, mn, mx, t)
                     for s, l, u, mn, mx, t in DUT_READ_SIGNALS
                     if t not in ("voltage", "current") and t != "diag"]
        for r2, (sig_name, label, unit, mn, mx, sig_type) in enumerate(non_meter):
            lbl    = QLabel(label + ":")
            lbl.setStyleSheet("color:#8b949e;")
            val_lbl = QLabel("—")
            val_lbl.setObjectName("value_label")
            u_lbl  = QLabel(unit)
            u_lbl.setObjectName("unit_label")
            grid.addWidget(lbl,     r2, 0)
            grid.addWidget(val_lbl, r2, 1)
            grid.addWidget(u_lbl,   r2, 2)
            self.read_labels[sig_name] = val_lbl

        rg_layout.addLayout(grid)

        # Diagnostic response frame display
        diag_grp = QGroupBox("Diagnostic Response Frame")
        diag_grp.setStyleSheet("QGroupBox{color:#d29922;border-color:#d29922;}")
        dg_layout = QVBoxLayout(diag_grp)

        self.diag_display = QTextEdit()
        self.diag_display.setReadOnly(True)
        self.diag_display.setFixedHeight(64)
        self.diag_display.setPlaceholderText("Awaiting diagnostic response…")
        dg_layout.addWidget(self.diag_display)
        rg_layout.addWidget(diag_grp)

        read_group.setLayout(rg_layout)
        splitter.addWidget(read_group)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter)

    # ── Signal sending ─────────────────────────────────────────────────────
    def _auto_send(self, sig_name, value):
        if self.db is None:
            return
        arb_id, data = encode_and_get_frame(self.db, sig_name, value)
        if arb_id is not None:
            self.send_requested.emit(1, arb_id, data)

    def _send_diag(self, sig_name):
        if self.db is None:
            return
        raw_text = self.write_spinboxes[sig_name].text().strip()
        try:
            val = int(raw_text, 16) if raw_text.startswith("0x") else int(raw_text)
        except ValueError:
            return
        arb_id, data = encode_and_get_frame(self.db, sig_name, val)
        if arb_id is not None:
            self.send_requested.emit(1, arb_id, data)

    # ── Update read values ─────────────────────────────────────────────────
    def update_signal(self, sig_name: str, value: float):
        if sig_name in self.meters:
            self.meters[sig_name].setValue(value)
        if sig_name in self.read_labels:
            self.read_labels[sig_name].setText(f"{value:.3f}")

        # Diagnostic response
        for sn, lbl, unit, mn, mx, sig_type in DUT_READ_SIGNALS:
            if sig_type == "diag" and sn == sig_name:
                self.diag_display.setText(
                    f"Signal : {sig_name}\n"
                    f"Value  : 0x{int(value):02X}  ({value})"
                )
                self.diag_timer.start(int(DIAG_DISPLAY_DURATION * 1000))

    def _clear_diag(self):
        self.diag_display.clear()

# ─────────────────────────────────────────────────────────────────────────────
# POWER SUPPLY PANEL
# ─────────────────────────────────────────────────────────────────────────────
class PowerSupplyPanel(QWidget):
    send_requested = pyqtSignal(int, int, bytes)

    def __init__(self, db, ps_index: int, prefix: str, parent=None):
        super().__init__(parent)
        self.db       = db
        self.ps_index = ps_index     # 1 or 2
        self.prefix   = prefix       # "PS1_" or "PS2_"
        self.write_widgets = {}
        self.read_labels   = {}
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        title = QLabel(f"Power Supply {self.ps_index}  –  CAN2  (Channel 4)")
        title.setStyleSheet("font-size:14px;font-weight:700;color:#a371f7;")
        root.addWidget(title)

        divider = QFrame(); divider.setObjectName("divider")
        root.addWidget(divider)

        splitter = QSplitter(Qt.Horizontal)

        # ── WRITE GROUP ────────────────────────────────────────────────────
        write_grp = QGroupBox(f"Write →  PS{self.ps_index}")
        write_grp.setStyleSheet("QGroupBox{color:#a371f7;border-color:#a371f7;}")
        wg = QGridLayout(write_grp)
        wg.setSpacing(8)

        for row, (suffix, label, unit, mn, mx, default, wtype) in \
                enumerate(PS_WRITE_SIGNALS):
            sig_name = self.prefix + suffix
            lbl = QLabel(label + ":")
            wg.addWidget(lbl, row, 0)

            if wtype == "switch":
                sw = ToggleSwitch("ON (1)", "OFF (2)")
                sw.setChecked(default == 1)
                sw.toggled.connect(
                    lambda checked, s=sig_name: self._send_val(s, 1 if checked else 2))
                self.write_widgets[sig_name] = sw
                wg.addWidget(sw, row, 1)

            elif wtype == "onoff":
                sw = ToggleSwitch("ON", "OFF")
                sw.setChecked(bool(default))
                sw.toggled.connect(
                    lambda checked, s=sig_name: self._send_val(s, 1 if checked else 0))
                self.write_widgets[sig_name] = sw
                wg.addWidget(sw, row, 1)

            else:   # spinbox
                sb = QDoubleSpinBox()
                sb.setRange(mn, mx)
                sb.setValue(default)
                sb.setSuffix(f"  {unit}" if unit else "")
                sb.setDecimals(1)
                sb.setFixedWidth(130)
                sb.valueChanged.connect(
                    lambda v, s=sig_name: self._send_val(s, v))
                self.write_widgets[sig_name] = sb
                wg.addWidget(sb, row, 1)

        splitter.addWidget(write_grp)

        # ── READ GROUP ─────────────────────────────────────────────────────
        read_grp = QGroupBox(f"Read ←  PS{self.ps_index}")
        read_grp.setStyleSheet("QGroupBox{color:#a371f7;border-color:#a371f7;}")
        rg = QGridLayout(read_grp)

        for r2, (suffix, label, unit, mn, mx) in enumerate(PS_READ_SIGNALS):
            sig_name = self.prefix + suffix
            rg.addWidget(QLabel(label + ":"), r2, 0)
            val_lbl = QLabel("—")
            val_lbl.setObjectName("value_label")
            rg.addWidget(val_lbl, r2, 1)
            rg.addWidget(QLabel(unit), r2, 2)
            self.read_labels[sig_name] = val_lbl

        splitter.addWidget(read_grp)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)

    def _send_val(self, sig_name, value):
        if self.db is None:
            return
        arb_id, data = encode_and_get_frame(self.db, sig_name, value)
        if arb_id is not None:
            self.send_requested.emit(2, arb_id, data)

    def update_signal(self, sig_name: str, value: float):
        if sig_name in self.read_labels:
            self.read_labels[sig_name].setText(f"{value:.3f}")

# ─────────────────────────────────────────────────────────────────────────────
# AUTOMATION PANEL
# ─────────────────────────────────────────────────────────────────────────────
class AutomationPanel(QWidget):
    send_requested = pyqtSignal(int, int, bytes)   # (bus_id, arb_id, data)

    def __init__(self, db_dut, db_ps, parent=None):
        super().__init__(parent)
        self.db_dut  = db_dut
        self.db_ps   = db_ps
        self._csv_rows  = []
        self._timer     = QTimer()
        self._timer.timeout.connect(self._tick)
        self._row_idx   = 0
        self._start_ts  = 0.0
        self._running   = False
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        title = QLabel("Automation  –  CSV Playback")
        title.setStyleSheet("font-size:15px;font-weight:700;color:#7ee787;")
        root.addWidget(title)

        # File picker
        file_row = QHBoxLayout()
        self.csv_path_edit = QLineEdit()
        self.csv_path_edit.setPlaceholderText("No CSV file selected…")
        self.csv_path_edit.setReadOnly(True)
        browse_btn = QPushButton("Browse CSV…")
        browse_btn.clicked.connect(self._browse)
        file_row.addWidget(self.csv_path_edit)
        file_row.addWidget(browse_btn)
        root.addLayout(file_row)

        # Info
        self.info_lbl = QLabel(
            "CSV format:  timestamp_ms, Signal1, Signal2, …\n"
            "First row must be headers. "
            "Signal names must match DBC signal names exactly."
        )
        self.info_lbl.setStyleSheet("color:#8b949e;font-size:11px;")
        root.addWidget(self.info_lbl)

        # Progress
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setStyleSheet(
            "QProgressBar{background:#21262d;border-radius:4px;height:18px;}"
            "QProgressBar::chunk{background:#238636;border-radius:4px;}"
        )
        root.addWidget(self.progress)

        # Status
        self.status_lbl = QLabel("Status: Idle")
        self.status_lbl.setStyleSheet("color:#8b949e;")
        root.addWidget(self.status_lbl)

        # Controls
        ctrl_row = QHBoxLayout()
        self.init_btn  = QPushButton("⚡  Initialise & Start")
        self.init_btn.setObjectName("btnSuccess")
        self.init_btn.clicked.connect(self._init_start)

        self.stop_btn  = QPushButton("■  Stop")
        self.stop_btn.setObjectName("btnDanger")
        self.stop_btn.clicked.connect(self._stop)
        self.stop_btn.setEnabled(False)

        ctrl_row.addWidget(self.init_btn)
        ctrl_row.addWidget(self.stop_btn)
        ctrl_row.addStretch()
        root.addLayout(ctrl_row)

        # Log
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(120)
        root.addWidget(self.log_view)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Automation CSV", "", "CSV Files (*.csv)")
        if path:
            self.csv_path_edit.setText(path)
            self._load_csv(path)

    def _load_csv(self, path):
        self._csv_rows = []
        try:
            with open(path, newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self._csv_rows.append(row)
            self.status_lbl.setText(
                f"Status: Loaded {len(self._csv_rows)} rows, "
                f"columns: {list(self._csv_rows[0].keys()) if self._csv_rows else []}"
            )
            self._log(f"CSV loaded: {len(self._csv_rows)} rows from {path}")
        except Exception as e:
            self._log(f"Error loading CSV: {e}")

    def _init_start(self):
        if not self._csv_rows:
            QMessageBox.warning(self, "No CSV", "Please load a CSV file first.")
            return
        self._row_idx  = 0
        self._running  = True
        self._start_ts = time.time() * 1000   # ms
        self.progress.setMaximum(len(self._csv_rows))
        self.progress.setValue(0)
        self._timer.start(10)   # 10ms tick resolution
        self.init_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_lbl.setText("Status: Running…")
        self._log("Automation started.")

    def _stop(self):
        self._timer.stop()
        self._running = False
        self.init_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_lbl.setText("Status: Stopped")
        self._log("Automation stopped.")

    def _tick(self):
        if self._row_idx >= len(self._csv_rows):
            self._stop()
            self.status_lbl.setText("Status: Complete ✔")
            self._log("Automation complete.")
            return

        now_ms   = time.time() * 1000 - self._start_ts
        row      = self._csv_rows[self._row_idx]

        try:
            target_ms = float(row.get("timestamp_ms", row.get("timestamp", 0)))
        except ValueError:
            target_ms = 0

        if now_ms < target_ms:
            return

        # Send all signals in this row
        for col, val_str in row.items():
            if col.lower() in ("timestamp_ms", "timestamp", "time_ms"):
                continue
            try:
                value = float(val_str)
            except ValueError:
                continue

            for db, bus_id in ((self.db_dut, 1), (self.db_ps, 2)):
                if db is None:
                    continue
                arb_id, data = encode_and_get_frame(db, col, value)
                if arb_id is not None:
                    self.send_requested.emit(bus_id, arb_id, data)
                    break

        self._row_idx += 1
        self.progress.setValue(self._row_idx)

    def _log(self, msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_view.append(f"[{ts}]  {msg}")

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING PANEL
# ─────────────────────────────────────────────────────────────────────────────
class LoggingPanel(QWidget):
    def __init__(self, db_dut, db_ps, parent=None):
        super().__init__(parent)
        self.db_dut      = db_dut
        self.db_ps       = db_ps
        self._log_file   = None
        self._csv_writer = None
        self._enabled    = False
        self._logged_cols = []
        self._selected   = set()
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        title = QLabel("Signal Logger")
        title.setStyleSheet("font-size:15px;font-weight:700;color:#d29922;")
        root.addWidget(title)

        # Signal selection
        sel_grp = QGroupBox("Select signals to log")
        sel_grp.setStyleSheet("QGroupBox{color:#d29922;border-color:#d29922;}")
        sel_layout = QVBoxLayout(sel_grp)

        # Search bar
        search_row = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter signals…")
        self.search_box.textChanged.connect(self._filter_signals)
        search_row.addWidget(QLabel("Search:"))
        search_row.addWidget(self.search_box)
        sel_layout.addLayout(search_row)

        # Scroll area for checkboxes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(200)
        self.checkbox_container = QWidget()
        self.checkbox_layout    = QVBoxLayout(self.checkbox_container)
        self.checkbox_layout.setSpacing(3)
        scroll.setWidget(self.checkbox_container)
        sel_layout.addWidget(scroll)

        # Populate checkboxes
        self.checkboxes = {}
        all_signals = self._collect_signals()
        for sig in sorted(all_signals):
            cb = QCheckBox(sig)
            cb.stateChanged.connect(lambda state, s=sig: self._toggle_signal(s, state))
            self.checkboxes[sig] = cb
            self.checkbox_layout.addWidget(cb)

        btn_row = QHBoxLayout()
        sel_all = QPushButton("Select All")
        sel_all.clicked.connect(lambda: [cb.setChecked(True) for cb in self.checkboxes.values()])
        sel_none = QPushButton("Select None")
        sel_none.clicked.connect(lambda: [cb.setChecked(False) for cb in self.checkboxes.values()])
        btn_row.addWidget(sel_all)
        btn_row.addWidget(sel_none)
        btn_row.addStretch()
        sel_layout.addLayout(btn_row)
        root.addWidget(sel_grp)

        # Output file
        out_row = QHBoxLayout()
        self.out_path = QLineEdit("can_log.csv")
        out_row.addWidget(QLabel("Output file:"))
        out_row.addWidget(self.out_path)
        out_browse = QPushButton("…")
        out_browse.setFixedWidth(30)
        out_browse.clicked.connect(self._browse_out)
        out_row.addWidget(out_browse)
        root.addLayout(out_row)

        # Controls
        ctrl_row = QHBoxLayout()
        self.start_btn = QPushButton("⏺  Start Logging")
        self.start_btn.setObjectName("btnSuccess")
        self.start_btn.clicked.connect(self._start_logging)
        self.stop_btn2 = QPushButton("⏹  Stop Logging")
        self.stop_btn2.setObjectName("btnDanger")
        self.stop_btn2.clicked.connect(self._stop_logging)
        self.stop_btn2.setEnabled(False)
        ctrl_row.addWidget(self.start_btn)
        ctrl_row.addWidget(self.stop_btn2)
        ctrl_row.addStretch()
        root.addLayout(ctrl_row)

        self.log_status = QLabel("Status: Idle")
        self.log_status.setStyleSheet("color:#8b949e;")
        root.addWidget(self.log_status)

        # Live log tail
        self.log_tail = QTextEdit()
        self.log_tail.setReadOnly(True)
        self.log_tail.setMinimumHeight(100)
        root.addWidget(self.log_tail)

    def _collect_signals(self):
        sigs = set()
        for db in (self.db_dut, self.db_ps):
            if db is None:
                continue
            for msg in db.messages:
                for sig in msg.signals:
                    sigs.add(sig.name)
        return sigs

    def _filter_signals(self, text):
        for sig, cb in self.checkboxes.items():
            cb.setVisible(text.lower() in sig.lower())

    def _toggle_signal(self, sig, state):
        if state == Qt.Checked:
            self._selected.add(sig)
        else:
            self._selected.discard(sig)

    def _browse_out(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save log as", "can_log.csv", "CSV (*.csv)")
        if path:
            self.out_path.setText(path)

    def _start_logging(self):
        if not self._selected:
            QMessageBox.warning(self, "No signals", "Select at least one signal to log.")
            return
        path = self.out_path.text()
        try:
            self._logged_cols = sorted(self._selected)
            self._log_file   = open(path, "w", newline="")
            self._csv_writer = csv.writer(self._log_file)
            self._csv_writer.writerow(["timestamp_ms"] + self._logged_cols)
            self._enabled    = True
            self.start_btn.setEnabled(False)
            self.stop_btn2.setEnabled(True)
            self.log_status.setText(f"Logging → {path}  ({len(self._logged_cols)} signals)")
            self._row_buffer = {s: None for s in self._logged_cols}
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _stop_logging(self):
        self._enabled = False
        if self._log_file:
            self._log_file.close()
            self._log_file = None
        self.start_btn.setEnabled(True)
        self.stop_btn2.setEnabled(False)
        self.log_status.setText("Status: Stopped  (file saved)")

    def ingest_signal(self, sig_name: str, value: float):
        """Called from main window whenever any signal arrives."""
        if not self._enabled or sig_name not in self._logged_cols:
            return
        ts_ms = int(time.time() * 1000)
        self._csv_writer.writerow([ts_ms, value])
        self._log_file.flush()
        self.log_tail.append(f"{ts_ms}  {sig_name} = {value:.4f}")

# ─────────────────────────────────────────────────────────────────────────────
# STATUS BAR WIDGET
# ─────────────────────────────────────────────────────────────────────────────
class StatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)

        self.led1 = LEDIndicator()
        self.led2 = LEDIndicator()
        self.lbl1 = QLabel("CAN1: —")
        self.lbl2 = QLabel("CAN2: —")
        self.msg_lbl = QLabel("")
        self.msg_lbl.setStyleSheet("color:#8b949e;")

        layout.addWidget(self.led1)
        layout.addWidget(self.lbl1)
        layout.addSpacing(20)
        layout.addWidget(self.led2)
        layout.addWidget(self.lbl2)
        layout.addStretch()
        layout.addWidget(self.msg_lbl)

        self.setStyleSheet("background:#161b22;border-top:1px solid #30363d;")

    def set_can1(self, ok):
        self.led1.setState(ok)
        self.lbl1.setText(f"CAN1: {'Connected' if ok else 'Disconnected'}")
        self.lbl1.setStyleSheet(f"color:{'#7ee787' if ok else '#f85149'};")

    def set_can2(self, ok):
        self.led2.setState(ok)
        self.lbl2.setText(f"CAN2: {'Connected' if ok else 'Disconnected'}")
        self.lbl2.setStyleSheet(f"color:{'#7ee787' if ok else '#f85149'};")

    def set_msg(self, msg):
        self.msg_lbl.setText(msg)

# ─────────────────────────────────────────────────────────────────────────────
# MAIN WINDOW
# ─────────────────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CAN Communication Suite  –  VN1640A")
        self.resize(1280, 820)
        self.setStyleSheet(DARK_STYLE)

        # Load DBC files
        self.db_dut = self._load_dbc(DBC_DUT_PATH, "DUT")
        self.db_ps  = self._load_dbc(DBC_PS_PATH,  "Power Supply")

        # CAN worker thread
        self._worker  = CANWorker(self.db_dut, self.db_ps,
                                  channel1=CAN1_HW_CH - 1,   # 0-indexed
                                  channel2=CAN2_HW_CH - 1)
        self._thread  = QThread()
        self._worker.moveToThread(self._thread)
        self._worker.signal_received.connect(self._on_signal)
        self._worker.frame_received.connect(self._on_frame)
        self._worker.connection_status.connect(self._on_conn_status)
        self._thread.started.connect(self._worker.run)

        self._build_ui()
        self._connect_buses()

    # ── DBC loading ────────────────────────────────────────────────────────
    def _load_dbc(self, path, name):
        if not os.path.isfile(path):
            logging.warning(f"{name} DBC not found at '{path}' – running in mock mode.")
            return None
        try:
            db = cantools.database.load_file(path)
            logging.info(f"{name} DBC loaded: {len(db.messages)} messages.")
            return db
        except Exception as e:
            logging.error(f"Failed to load {name} DBC: {e}")
            return None

    # ── UI construction ────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        vbox = QVBoxLayout(central)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # Header bar
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet("background:#161b22;border-bottom:1px solid #30363d;")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(16, 0, 16, 0)
        title_lbl = QLabel("⚡  CAN Communication Suite")
        title_lbl.setStyleSheet(
            "font-size:17px;font-weight:700;"
            "color:#58a6ff;font-family:'Segoe UI';")
        hw_lbl = QLabel("VN1640A  ·  Vector XL")
        hw_lbl.setStyleSheet("color:#8b949e;font-size:12px;")
        h_lay.addWidget(title_lbl)
        h_lay.addStretch()
        h_lay.addWidget(hw_lbl)

        reconnect_btn = QPushButton("⟳  Reconnect")
        reconnect_btn.clicked.connect(self._connect_buses)
        h_lay.addSpacing(12)
        h_lay.addWidget(reconnect_btn)
        vbox.addWidget(header)

        # Main tab widget
        self.tabs = QTabWidget()
        vbox.addWidget(self.tabs)

        # ── DUT Tab ────────────────────────────────────────────────────────
        self.dut_panel = DUTPanel(self.db_dut)
        self.dut_panel.send_requested.connect(self._send_frame)
        self._wrap_tab(self.dut_panel, "🔧  DUT")

        # ── PS1 Tab ────────────────────────────────────────────────────────
        self.ps1_panel = PowerSupplyPanel(self.db_ps, 1, PS1_PREFIX)
        self.ps1_panel.send_requested.connect(self._send_frame)
        self._wrap_tab(self.ps1_panel, "⚡  Power Supply 1")

        # ── PS2 Tab ────────────────────────────────────────────────────────
        self.ps2_panel = PowerSupplyPanel(self.db_ps, 2, PS2_PREFIX)
        self.ps2_panel.send_requested.connect(self._send_frame)
        self._wrap_tab(self.ps2_panel, "⚡  Power Supply 2")

        # ── Overview Tab (all 3 side-by-side) ─────────────────────────────
        overview = QWidget()
        ov_lay   = QHBoxLayout(overview)
        ov_lay.setContentsMargins(6, 6, 6, 6)
        ov_lay.setSpacing(6)

        # Mini DUT
        mini_dut = self._mini_dut()
        ov_lay.addWidget(mini_dut, 2)

        sep1 = QFrame(); sep1.setFrameShape(QFrame.VLine)
        sep1.setStyleSheet("color:#30363d;")
        ov_lay.addWidget(sep1)

        mini_ps1 = self._mini_ps(1, PS1_PREFIX)
        ov_lay.addWidget(mini_ps1, 1)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet("color:#30363d;")
        ov_lay.addWidget(sep2)

        mini_ps2 = self._mini_ps(2, PS2_PREFIX)
        ov_lay.addWidget(mini_ps2, 1)

        self.tabs.addTab(overview, "📊  Overview")

        # ── Automation Tab ─────────────────────────────────────────────────
        self.auto_panel = AutomationPanel(self.db_dut, self.db_ps)
        self.auto_panel.send_requested.connect(self._send_frame)
        scroll_auto = QScrollArea()
        scroll_auto.setWidgetResizable(True)
        scroll_auto.setWidget(self.auto_panel)
        self.tabs.addTab(scroll_auto, "🤖  Automation")

        # ── Logging Tab ────────────────────────────────────────────────────
        self.log_panel = LoggingPanel(self.db_dut, self.db_ps)
        scroll_log = QScrollArea()
        scroll_log.setWidgetResizable(True)
        scroll_log.setWidget(self.log_panel)
        self.tabs.addTab(scroll_log, "📋  Logging")

        # Status bar
        self.status_bar = StatusBar()
        vbox.addWidget(self.status_bar)

        # Keep overview meter references
        self.overview_meters_dut = {}
        self.overview_ps1_labels = {}
        self.overview_ps2_labels = {}

    def _wrap_tab(self, widget, label):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        self.tabs.addTab(scroll, label)

    def _mini_dut(self):
        grp = QGroupBox("DUT  (CAN1)")
        lay = QVBoxLayout(grp)
        meters_row = QHBoxLayout()
        self.overview_meters_dut = {}
        for sig_name, label, unit, mn, mx, sig_type in DUT_READ_SIGNALS:
            if sig_type in ("voltage", "current"):
                m = AnalogMeter(label, unit, mn, mx, sig_type)
                self.overview_meters_dut[sig_name] = m
                meters_row.addWidget(m)
        lay.addLayout(meters_row)
        return grp

    def _mini_ps(self, idx, prefix):
        grp = QGroupBox(f"PS{idx}  (CAN2)")
        grp.setStyleSheet("QGroupBox{color:#a371f7;border-color:#a371f7;}")
        lay = QGridLayout(grp)
        store = self.overview_ps1_labels if idx == 1 else self.overview_ps2_labels
        for r2, (suffix, label, unit, mn, mx) in enumerate(PS_READ_SIGNALS):
            sig_name = prefix + suffix
            lay.addWidget(QLabel(label + ":"), r2, 0)
            v = QLabel("—")
            v.setObjectName("value_label")
            lay.addWidget(v, r2, 1)
            lay.addWidget(QLabel(unit), r2, 2)
            store[sig_name] = v
        return grp

    # ── CAN connection ─────────────────────────────────────────────────────
    def _connect_buses(self):
        self.status_bar.set_msg("Connecting…")
        if not self._thread.isRunning():
            self._thread.start()
        else:
            # Re-init worker's buses
            QTimer.singleShot(0, self._worker.connect_buses)
        QTimer.singleShot(100, self._worker.connect_buses)

    def _on_conn_status(self, ok, msg):
        self.status_bar.set_can1(ok)
        self.status_bar.set_can2(ok)
        self.status_bar.set_msg(msg)

    # ── Signal routing ─────────────────────────────────────────────────────
    def _on_signal(self, sig_name: str, value: float):
        self.dut_panel.update_signal(sig_name, value)
        self.ps1_panel.update_signal(sig_name, value)
        self.ps2_panel.update_signal(sig_name, value)
        self.log_panel.ingest_signal(sig_name, value)

        # Overview meters
        if sig_name in self.overview_meters_dut:
            self.overview_meters_dut[sig_name].setValue(value)
        if sig_name in self.overview_ps1_labels:
            self.overview_ps1_labels[sig_name].setText(f"{value:.3f}")
        if sig_name in self.overview_ps2_labels:
            self.overview_ps2_labels[sig_name].setText(f"{value:.3f}")

    def _on_frame(self, arb_id: int, data: bytes):
        pass   # extend for raw-frame display if needed

    def _send_frame(self, bus_id: int, arb_id: int, data: bytes):
        self._worker.send(bus_id, arb_id, data)
        self.status_bar.set_msg(
            f"Sent  ID=0x{arb_id:03X}  [{data.hex(' ').upper()}]  on CAN{bus_id}"
        )

    # ── Cleanup ────────────────────────────────────────────────────────────
    def closeEvent(self, event):
        self._worker.stop()
        self._thread.quit()
        self._thread.wait(2000)
        event.accept()


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
def main():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S"
    )
    app = QApplication(sys.argv)
    app.setApplicationName("CAN Communication Suite")
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
