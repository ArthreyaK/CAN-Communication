"""
CAN Communication GUI  –  Hardware Version  (VN1640A via python-can Vector XL)
Requires:  PyQt5  python-can  cantools
DBC files: IT6000-127-V2_4.dbc   (PS1)
           IT6000-127-V2_4_PS2.dbc (PS2)
           DUT.dbc
CAN Channel Assignment:
  CH3 (CAN1) → DUT  (Vehicle DCDC Converter)
  CH4 (CAN2) → PS1 + PS2  (IT6000 Power Supplies)
Run:  python can_gui_hw.py
"""

import sys, os, csv, struct, threading, time, math, random
from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout,
    QHBoxLayout, QGridLayout, QLabel, QDoubleSpinBox, QSpinBox,
    QComboBox, QPushButton, QGroupBox, QScrollArea, QFileDialog,
    QTextEdit, QCheckBox, QLineEdit, QProgressBar, QSizePolicy,
    QFrame, QButtonGroup, QRadioButton
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread, QRectF, QPointF
from PyQt5.QtGui import QFont, QPainter, QPen, QBrush, QRadialGradient, QFontMetrics, QColor

try:
    import can
    import cantools
    HW_AVAILABLE = True
except ImportError:
    HW_AVAILABLE = False
    print("WARNING: python-can or cantools not installed – hardware unavailable")

SCRIPT_DIR = Path(__file__).parent
PS1_DBC = SCRIPT_DIR / "IT6000-127-V2_4.dbc"
PS2_DBC = SCRIPT_DIR / "IT6000-127-V2_4_PS2.dbc"
DUT_DBC = SCRIPT_DIR / "DUT.dbc"

# CH4 = CAN2 = Power Supplies
PS1_IDS = dict(NMT=0x000, RPDO1=0x27F, RPDO2=0x37F, SDO=0x67F, TPDO1=0x1FF)
PS2_IDS = dict(NMT=0x000, RPDO1=0x275, RPDO2=0x375, SDO=0x675, TPDO1=0x1F5)

SDO_MUX = {
    "SDO_Server_DC_Current_Fall":      120587043,
    "SDO_Server_DC_Current_Rise":      103809827,
    "SDO_Server_DC_Voltage_Fall":      70255395,
    "SDO_Server_DC_Voltage_Rise":      53478179,
    "SDO_Server_DC_Output_Resistance": 305136419,
    "SDO_Server_DC_Voltage_High":      137364259,
    "SDO_Server_DC_Voltage_Low":       154141475,
    "SDO_Server_DC_Current_High":      170918691,
    "SDO_Server_DC_Current_Low":       187695907,
    "SDO_Server_OnOff":                70255139,
}

# CH3 = CAN1 = DUT
DUT_DIAG_REQ_ID   = 1875   # TST_PhysicalReqEPICD_PMZ  (0x753)
DUT_DIAG_RESP_ID  = 1883   # TST_PhysicalRespEPICD_PMZ (0x75B)
DUT_DIAG_REQ_MSG  = "TST_PhysicalReqEPICD_PMZ"
DUT_DIAG_RESP_MSG = "TST_PhysicalRespEPICD_PMZ"
DUT_DIAG_REQ_SIG  = "TST_PhysicalReqEPICD_PDU"
DUT_DIAG_RESP_SIG = "TST_PhysicalRespEPICD_PDU"

OPMODE_VALUES = [
    (0, "Standby"),
    (1, "Buck Mode"),
    (2, "Reserved (Boost)"),
    (3, "Bus Discharge"),
    (4, "Bus Test Mode"),
    (5, "Not Used 5"),
    (6, "Not Used 6"),
    (7, "Not Used 7"),
]

PS_WRITE_SIGNALS = [
    ("dc_mode",             "RPDO1", "dc_mode",            0,  0,   1,     1,     "0=CV 1=CC"),
    ("dc_voltage (V)",      "RPDO1", "dc_voltage",         0,  0,   100,   0.001, "V"),
    ("dc_current (A)",      "RPDO2", "dc_current",         0, -100, 100,   0.001, "A"),
    ("DC_Current_Fall (ms)", "SDO",   "SDO_Server_DC_Current_Fall",   0,-999,999,0.001,"ms"),
    ("DC_Current_Rise (ms)", "SDO",   "SDO_Server_DC_Current_Rise",   0,-999,999,0.001,"ms"),
    ("DC_Voltage_Fall (ms)", "SDO",   "SDO_Server_DC_Voltage_Fall",   0,-999,999,0.001,"ms"),
    ("DC_Voltage_Rise (ms)", "SDO",   "SDO_Server_DC_Voltage_Rise",   0,-999,999,0.001,"ms"),
    ("DC_Output_Res (mΩ)",   "SDO",   "SDO_Server_DC_Output_Resistance",0,-999,999,0.001,"mΩ"),
    ("DC_Voltage_High (V)", "SDO",   "SDO_Server_DC_Voltage_High",   0,-999,999,0.001,"V"),
    ("DC_Voltage_Low (V)",  "SDO",   "SDO_Server_DC_Voltage_Low",    0,-999,999,0.001,"V"),
    ("DC_Current_High (A)", "SDO",   "SDO_Server_DC_Current_High",   0,-999,999,0.001,"A"),
    ("DC_Current_Low (A)",  "SDO",   "SDO_Server_DC_Current_Low",    0,-999,999,0.001,"A"),
]

PS_READ_SIGNALS = [
    ("Meter_volt (V)",  "TPDO1", "Meter_volt"),
    ("Meter_curr (A)",  "TPDO1", "Meter_curr"),
    ("Meter_power (W)", "TPDO2", "Meter_power"),
]

DUT_READ_SIGNALS = [
    ("DCDCOperatingModeExt2", "DCDCOpModeMV",   "DCDCOperatingModeExt2"),
    ("DCDCVoltageMV (V)",     "DCDCOpModeMV",   "DCDCVoltageMV"),
    ("DCDCCurrentMV (A)",     "DCDCOpModeMV",   "DCDCCurrentMV"),
    ("DCDC12vActualCurrent (A)",  "HVDCDC_PMZ_12v", "DCDC12vActualCurrent"),
    ("DCDC12vActualVoltage (V)",  "HVDCDC_PMZ_12v", "DCDC12vActualVoltage"),
]

DUT_WRITE_SIGNALS = [
    ("DCDCVoltageMVRequest(V)",  "PCM_PMZ_DCDCControl", "DCDCVoltageMVRequest",  0,  0,    102.1, 0.1, "V"),
    ("DCDCCurrentMVLimit(A)",    "PCM_PMZ_DCDCControl", "DCDCCurrentMVLimit",    0, -102.35,102.35,0.1,"A"),
    ("DCDC12vSetpointRequest (V)",   "GWM_PMZ_CoreSystem",  "DCDC12vSetpointRequest",0,  0,     25.3, 0.1, "V"),
    ("CrashStatusRCM",           "RCM_FR_PR_GW_1_PMZ",  "CrashStatusRCM",        0,  0,      1,   1,  "0=No 1=Crash"),
    ("PowerMode",                "BCM_PMZ_Core",        "PowerMode",             0,  0,     31,   1,  "0=KeyOut"),
]


# ═══════════════════════════════════════════════════════════════════════════════
#  Analog Meter
# ═══════════════════════════════════════════════════════════════════════════════
class AnalogMeter(QWidget):
    def __init__(self, label, unit, min_val, max_val, parent=None):
        super().__init__(parent)
        self.label = label; self.unit = unit
        self.min_val = min_val; self.max_val = max_val
        self._value = min_val
        self.setMinimumSize(140, 140); self.setMaximumSize(160, 160)

    def setValue(self, v):
        self._value = max(self.min_val, min(self.max_val, v)); self.update()

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        cx, cy = w / 2, h * 0.54
        radius = min(w, h) * 0.42
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        grad = QRadialGradient(cx, cy, radius)
        grad.setColorAt(0, QColor("#1a1a2e")); grad.setColorAt(1, QColor("#0d0d1a"))
        painter.setBrush(QBrush(grad)); painter.setPen(QPen(QColor("#3a3a5c"), 2))
        painter.drawEllipse(QRectF(cx-radius, cy-radius, radius*2, radius*2))
        start_angle, span_angle = 220, 280
        arc_r = radius * 0.82
        arc_rect = QRectF(cx-arc_r, cy-arc_r, arc_r*2, arc_r*2)
        painter.setPen(QPen(QColor("#2a2a4a"), 5, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(arc_rect, int((180-start_angle)*16), int(-span_angle*16))
        frac = max(0.0, min(1.0, (self._value-self.min_val)/max(1e-9, self.max_val-self.min_val)))
        r = int(frac*2*255) if frac < 0.5 else 255
        g = 220 if frac < 0.5 else int((1-(frac-0.5)*2)*220)
        painter.setPen(QPen(QColor(r, g, 40), 5, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(arc_rect, int((180-start_angle)*16), int(-frac*span_angle*16))
        for i in range(11):
            a_rad = math.radians(start_angle - i*(span_angle/10))
            is_major = (i % 2 == 0)
            t_out = radius*0.88; t_in = radius*(0.74 if is_major else 0.80)
            painter.setPen(QPen(QColor("#6060aa"), 2 if is_major else 1))
            painter.drawLine(QPointF(cx+t_out*math.cos(a_rad), cy-t_out*math.sin(a_rad)),
                             QPointF(cx+t_in*math.cos(a_rad),  cy-t_in*math.sin(a_rad)))
        n_rad = math.radians(start_angle - frac*span_angle)
        nl = radius*0.70
        painter.setPen(QPen(QColor("#ff4444"), 2.5, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(cx, cy), QPointF(cx+nl*math.cos(n_rad), cy-nl*math.sin(n_rad)))
        painter.setBrush(QBrush(QColor("#ff4444"))); painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(cx-4, cy-4, 8, 8))
        painter.setPen(QColor("#e0e8ff"))
        fnt = QFont("Consolas", 10, QFont.Bold); painter.setFont(fnt)
        val_txt = f"{self._value:.1f}"
        fm = QFontMetrics(fnt); tw = fm.horizontalAdvance(val_txt)
        painter.drawText(int(cx-tw/2), int(cy+radius*0.45), val_txt)
        painter.setPen(QColor("#7080a0"))
        fnt2 = QFont("Consolas", 8); painter.setFont(fnt2)
        fm2 = QFontMetrics(fnt2); uw = fm2.horizontalAdvance(self.unit)
        painter.drawText(int(cx-uw/2), int(cy+radius*0.62), self.unit)
        painter.setPen(QColor("#8899cc"))
        fnt3 = QFont("Consolas", 7, QFont.Bold); painter.setFont(fnt3)
        fm3 = QFontMetrics(fnt3); lw = fm3.horizontalAdvance(self.label)
        painter.drawText(int(cx-lw/2), int(cy-radius*0.55), self.label)


# ═══════════════════════════════════════════════════════════════════════════════
#  Toggle Switch
# ═══════════════════════════════════════════════════════════════════════════════
class ToggleSwitch(QWidget):
    toggled = pyqtSignal(bool)
    def __init__(self, label_on="ON", label_off="OFF", initial=False, parent=None):
        super().__init__(parent)
        self._state = initial; self._label_on = label_on; self._label_off = label_off
        self.setFixedSize(90, 34); self.setCursor(Qt.PointingHandCursor)
    def isChecked(self): return self._state
    def setState(self, state, emit=True):
        if self._state != state:
            self._state = state; self.update()
            if emit: self.toggled.emit(self._state)
    def mousePressEvent(self, event):
        self._state = not self._state; self.update(); self.toggled.emit(self._state)
    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height(); r = h*0.45
        p.setBrush(QBrush(QColor("#1aaa55") if self._state else QColor("#c0392b"))); p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(0, (h-h*0.55)/2, w, h*0.55), r, r)
        knob_x = w-h*0.6-2 if self._state else 2
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawEllipse(QRectF(knob_x, 2, h-4, h-4))
        p.setPen(QColor("#ffffff"))
        fnt = QFont("Consolas", 8, QFont.Bold); p.setFont(fnt)
        txt = self._label_on if self._state else self._label_off
        fm = QFontMetrics(fnt); tw = fm.horizontalAdvance(txt)
        txt_x = 5 if self._state else w-tw-5
        p.drawText(int(txt_x), int(h*0.68), txt)


# ═══════════════════════════════════════════════════════════════════════════════
#  Hex Byte Entry (single byte box)
# ═══════════════════════════════════════════════════════════════════════════════
class HexByteEntry(QLineEdit):
    next_focus = pyqtSignal()
    prev_focus = pyqtSignal()
    def __init__(self):
        super().__init__()
        self.setMaxLength(2); self.setFixedWidth(30); self.setAlignment(Qt.AlignCenter)
        self.setPlaceholderText("00")
        self.setStyleSheet(
            "background:#0d1117;color:#00ff88;border:1px solid #3a5a8a;"
            "border-radius:3px;font-family:Consolas;font-size:13px;font-weight:bold;")
        self.textChanged.connect(self._on_text_changed)
    def _on_text_changed(self, text):
        filtered = ''.join(c for c in text.upper() if c in '0123456789ABCDEF')
        if filtered != text.upper(): self.setText(filtered); return
        if len(filtered) == 2: self.next_focus.emit()
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Backspace and len(self.text()) == 0: self.prev_focus.emit()
        super().keyPressEvent(event)
    def value_byte(self):
        t = self.text().strip()
        if not t: return 0
        return int(t, 16) if all(c in '0123456789ABCDEFabcdef' for c in t) else 0


# ═══════════════════════════════════════════════════════════════════════════════
#  8-byte Hex Entry Widget (write)
# ═══════════════════════════════════════════════════════════════════════════════
class DiagnosticsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self); lay.setSpacing(4); lay.setContentsMargins(0,0,0,0)
        self._entries = []
        for i in range(8):
            entry = HexByteEntry(); self._entries.append(entry); lay.addWidget(entry)
            if i < 7:
                sep = QLabel("·"); sep.setStyleSheet("color:#3a5a8a;font-size:14px;"); lay.addWidget(sep)
        for i, e in enumerate(self._entries):
            if i < 7: e.next_focus.connect(self._entries[i+1].setFocus)
            if i > 0: e.prev_focus.connect(self._entries[i-1].setFocus)
    def get_bytes(self): return bytes([e.value_byte() for e in self._entries])
    def clear(self):
        for e in self._entries: e.clear()


# ═══════════════════════════════════════════════════════════════════════════════
#  8-byte Hex Display Widget (read, read-only)
# ═══════════════════════════════════════════════════════════════════════════════
class HexDisplayWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self); lay.setSpacing(4); lay.setContentsMargins(0,0,0,0)
        self._boxes = []
        for i in range(8):
            box = QLineEdit("--"); box.setReadOnly(True)
            box.setFixedWidth(30); box.setAlignment(Qt.AlignCenter)
            box.setStyleSheet(
                "background:#060a10;color:#00ccff;border:1px solid #1e3a5a;"
                "border-radius:3px;font-family:Consolas;font-size:13px;font-weight:bold;")
            self._boxes.append(box); lay.addWidget(box)
            if i < 7:
                sep = QLabel("·"); sep.setStyleSheet("color:#1e3a5a;font-size:14px;"); lay.addWidget(sep)
    def set_bytes(self, data: bytes):
        for i, b in enumerate(data[:8]):
            self._boxes[i].setText(f"{b:02X}")
    def clear(self):
        for b in self._boxes: b.setText("--")


# ═══════════════════════════════════════════════════════════════════════════════
#  Stylesheet
# ═══════════════════════════════════════════════════════════════════════════════
DARK_SS = """
QMainWindow, QWidget { background:#0a0e1a; color:#c8d8f0; font-family:'Consolas',monospace; }
QTabWidget::pane { border:1px solid #1e3a5a; background:#0a0e1a; }
QTabBar::tab { background:#111827; color:#8899bb; padding:7px 16px; border:1px solid #1e3a5a; border-bottom:none; font-size:11px; }
QTabBar::tab:selected { background:#1e3a5a; color:#00d4ff; border-top:2px solid #00d4ff; }
QGroupBox { border:1px solid #1e3a5a; border-radius:6px; margin-top:12px; color:#00aaff; font-weight:bold; font-size:11px; background:#0c1221; }
QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 6px; color:#00d4ff; }
QPushButton { background:#111827; color:#c8d8f0; border:1px solid #2a4a7a; border-radius:4px; padding:5px 12px; font-size:11px; }
QPushButton:hover { background:#1e2d4a; border-color:#00aaff; }
QPushButton:pressed { background:#0055aa; color:#ffffff; }
QPushButton#sendBtn  { background:#0d3322; color:#00ff88; border-color:#00aa55; }
QPushButton#diagBtn  { background:#1a1a00; color:#ffdd00; border:1px solid #aaaa00; border-radius:4px; padding:5px 14px; font-size:11px; font-weight:bold; }
QPushButton#diagBtn:hover  { background:#2a2a00; border-color:#ffff00; }
QPushButton#diagBtn:pressed { background:#444400; }
QPushButton#startBtn { background:#0d3322; color:#00ff88; border:1px solid #00aa55; }
QPushButton#stopBtn  { background:#3a0d0d; color:#ff4444; border:1px solid #aa2222; }
QDoubleSpinBox, QSpinBox, QComboBox, QLineEdit { background:#0d1117; color:#c8d8f0; border:1px solid #2a4a7a; border-radius:3px; padding:3px 6px; font-family:Consolas; }
QDoubleSpinBox:focus, QLineEdit:focus { border-color:#00aaff; }
QLabel#readVal { color:#00ff88; font-weight:bold; font-size:12px; font-family:Consolas; }
QLabel#rxHex   { color:#00ccff; font-weight:bold; font-size:12px; font-family:Consolas; }
QTextEdit { background:#060a10; color:#00ff88; font-family:Consolas,monospace; border:1px solid #1e3a5a; }
QCheckBox { color:#c8d8f0; }
QCheckBox::indicator { width:14px; height:14px; border:1px solid #2a4a7a; background:#0d1117; border-radius:3px; }
QCheckBox::indicator:checked { background:#00aaff; border-color:#00aaff; }
QProgressBar { border:1px solid #2a4a7a; border-radius:3px; background:#0d1117; text-align:center; color:#c8d8f0; }
QProgressBar::chunk { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #004488,stop:1 #00aaff); }
QScrollBar:vertical   { background:#0a0e1a; width:10px; }
QScrollBar::handle:vertical   { background:#1e3a5a; border-radius:5px; min-height:20px; }
QScrollBar:horizontal { background:#0a0e1a; height:10px; }
QScrollBar::handle:horizontal { background:#1e3a5a; border-radius:5px; min-width:20px; }
QRadioButton { color:#c8d8f0; spacing:6px; }
QRadioButton::indicator { width:14px; height:14px; border:1px solid #2a4a7a; border-radius:7px; background:#0d1117; }
QRadioButton::indicator:checked { background:#00aaff; border-color:#00aaff; }
"""


# ═══════════════════════════════════════════════════════════════════════════════
#  CAN Worker  –  CH3 = DUT (bus_dut),  CH4 = PS1+PS2 (bus_ps)
# ═══════════════════════════════════════════════════════════════════════════════
class CANWorker(QObject):
    rx_data = pyqtSignal(dict)   # {msg_name: {sig_name: value}}
    rx_diag = pyqtSignal(bytes)  # raw 8-byte diagnostic response
    status  = pyqtSignal(str)

    def __init__(self, dbc_ps1, dbc_ps2, dbc_dut):
        super().__init__()
        self.dbc_ps1 = dbc_ps1; self.dbc_ps2 = dbc_ps2; self.dbc_dut = dbc_dut
        self._running = False
        self.bus_dut = None   # CH3 – DUT
        self.bus_ps  = None   # CH4 – PS1 + PS2

    def start_buses(self):
        try:
            self.bus_dut = can.interface.Bus(bustype="vector", channel=2,
                                             bitrate=500000, app_name="CANalyzer")  # CH3 = index 2
            self.bus_ps  = can.interface.Bus(bustype="vector", channel=3,
                                             bitrate=500000, app_name="CANalyzer")  # CH4 = index 3
            self._running = True
            self.status.emit("CAN buses connected  [CH3→DUT | CH4→PS1+PS2]")
        except Exception as e:
            self.status.emit(f"Bus error: {e}")

    def stop_buses(self):
        self._running = False
        for bus in (self.bus_dut, self.bus_ps):
            if bus:
                try: bus.shutdown()
                except: pass

    def receive_loop(self):
        while self._running:
            # DUT bus (CH3)
            if self.bus_dut:
                try:
                    msg = self.bus_dut.recv(timeout=0.005)
                    if msg is not None:
                        # Check for diagnostic response
                        if msg.arbitration_id == DUT_DIAG_RESP_ID:
                            self.rx_diag.emit(bytes(msg.data))
                        elif self.dbc_dut:
                            try:
                                frame   = self.dbc_dut.get_message_by_frame_id(msg.arbitration_id)
                                decoded = frame.decode(msg.data, decode_choices=False)
                                self.rx_data.emit({frame.name: decoded})
                            except: pass
                except: pass
            # PS bus (CH4)
            if self.bus_ps:
                try:
                    msg = self.bus_ps.recv(timeout=0.005)
                    if msg is not None:
                        for db in (self.dbc_ps1, self.dbc_ps2):
                            if db is None: continue
                            try:
                                frame   = db.get_message_by_frame_id(msg.arbitration_id)
                                decoded = frame.decode(msg.data, decode_choices=False)
                                self.rx_data.emit({frame.name: decoded})
                                break
                            except: pass
                except: pass

    def _send(self, bus, arb_id, data_bytes):
        if bus is None: return
        try:
            bus.send(can.Message(arbitration_id=arb_id, data=data_bytes, is_extended_id=False))
        except Exception as e:
            self.status.emit(f"TX error 0x{arb_id:X}: {e}")

    def send_nmt(self, ps_idx, value):
        ids = PS1_IDS if ps_idx == 1 else PS2_IDS
        self._send(self.bus_ps, ids["NMT"], bytes([int(value), 0x7F]))

    def send_onoff(self, ps_idx, value):
        self.send_sdo(ps_idx, "SDO_Server_OnOff", value)

    def send_rpdo1(self, ps_idx, db, dc_mode, dc_voltage):
        ids = PS1_IDS if ps_idx == 1 else PS2_IDS
        try:
            frame = db.get_message_by_frame_id(ids["RPDO1"])
            self._send(self.bus_ps, ids["RPDO1"],
                       frame.encode({"dc_mode": int(dc_mode), "dc_voltage": float(dc_voltage)}))
        except Exception as e: self.status.emit(f"RPDO1 error: {e}")

    def send_rpdo2(self, ps_idx, db, dc_current):
        ids = PS1_IDS if ps_idx == 1 else PS2_IDS
        try:
            frame = db.get_message_by_frame_id(ids["RPDO2"])
            self._send(self.bus_ps, ids["RPDO2"], frame.encode({"dc_current": float(dc_current)}))
        except Exception as e: self.status.emit(f"RPDO2 error: {e}")

    def send_sdo(self, ps_idx, signal_name, value):
        ids    = PS1_IDS if ps_idx == 1 else PS2_IDS
        mux_id = SDO_MUX.get(signal_name)
        if mux_id is None: return
        raw_val = int(round(float(value) / 0.001))
        self._send(self.bus_ps, ids["SDO"],
                   struct.pack("<II", mux_id & 0xFFFFFFFF, raw_val & 0xFFFFFFFF))

    def send_dut(self, msg_name, signal_dict):
        if self.bus_dut is None or self.dbc_dut is None: return
        try:
            frame    = self.dbc_dut.get_message_by_name(msg_name)
            sig_dict = {s.name: 0 for s in frame.signals}
            sig_dict.update(signal_dict)
            self._send(self.bus_dut, frame.frame_id, frame.encode(sig_dict))
        except Exception as e: self.status.emit(f"DUT TX {msg_name}: {e}")

    def send_diag_request(self, raw_bytes: bytes):
        """Send 8-byte raw diagnostic request on CH3."""
        self._send(self.bus_dut, DUT_DIAG_REQ_ID, raw_bytes[:8])


# ═══════════════════════════════════════════════════════════════════════════════
#  PS Section Widget
# ═══════════════════════════════════════════════════════════════════════════════
class PSSection(QGroupBox):
    values_changed = pyqtSignal(int, str, str, float)

    def __init__(self, title, ps_idx, parent=None):
        super().__init__(title, parent)
        self.ps_idx = ps_idx
        self._write_widgets = {}
        self._meters        = {}
        self._nmt_state     = False
        self._onoff_state   = False
        self._build()

    def _build(self):
        main = QVBoxLayout(self); main.setSpacing(6)

        m_grp = QGroupBox("Live Readings")
        m_lay = QHBoxLayout(m_grp); m_lay.setSpacing(6)
        self._meter_volt  = AnalogMeter("VOLTAGE", "V",   0,  100)
        self._meter_curr  = AnalogMeter("CURRENT", "A", -100, 100)
        self._meter_power = AnalogMeter("POWER",   "W",   0, 10000)
        for m in (self._meter_volt, self._meter_curr, self._meter_power): m_lay.addWidget(m)
        self._meters = {"Meter_volt": self._meter_volt,
                        "Meter_curr": self._meter_curr,
                        "Meter_power": self._meter_power}
        main.addWidget(m_grp)

        ctrl_grp = QGroupBox("Control")
        ctrl_lay = QHBoxLayout(ctrl_grp)
        ctrl_lay.addWidget(QLabel("NMT:"))
        self._nmt_toggle = ToggleSwitch("ON(1)", "OFF(2)", initial=False)
        self._nmt_toggle.toggled.connect(self._nmt_changed)
        ctrl_lay.addWidget(self._nmt_toggle)
        self._nmt_lbl = QLabel("OFF"); self._nmt_lbl.setStyleSheet("color:#ff4444;font-weight:bold;font-size:11px;")
        ctrl_lay.addWidget(self._nmt_lbl)
        ctrl_lay.addSpacing(16)
        ctrl_lay.addWidget(QLabel("OnOff:"))
        self._onoff_toggle = ToggleSwitch("ON", "OFF", initial=False)
        self._onoff_toggle.toggled.connect(self._onoff_changed)
        ctrl_lay.addWidget(self._onoff_toggle)
        self._onoff_lbl = QLabel("OFF"); self._onoff_lbl.setStyleSheet("color:#ff4444;font-weight:bold;font-size:11px;")
        ctrl_lay.addWidget(self._onoff_lbl)
        ctrl_lay.addStretch()
        main.addWidget(ctrl_grp)

        w_grp = QGroupBox("Write Setpoints")
        w_lay = QGridLayout(w_grp); w_lay.setSpacing(4)
        for row, (label, fk, sig, default, mn, mx, step, unit) in enumerate(PS_WRITE_SIGNALS):
            w_lay.addWidget(QLabel(label), row, 0)
            sb = QDoubleSpinBox(); sb.setRange(mn, mx); sb.setSingleStep(step)
            sb.setDecimals(3); sb.setValue(default); sb.setMinimumWidth(100)
            self._write_widgets[sig] = sb
            w_lay.addWidget(sb, row, 1)
            w_lay.addWidget(QLabel(unit), row, 2)
        main.addWidget(w_grp)

    def _nmt_changed(self, state):
        self._nmt_state = state
        self.values_changed.emit(self.ps_idx, "NMT", "NMT_CS", 1.0 if state else 2.0)
        c = "#00ff88" if state else "#ff4444"
        self._nmt_lbl.setText("ON" if state else "OFF")
        self._nmt_lbl.setStyleSheet(f"color:{c};font-weight:bold;font-size:11px;")

    def _onoff_changed(self, state):
        self._onoff_state = state
        self.values_changed.emit(self.ps_idx, "SDO", "SDO_Server_OnOff", 1.0 if state else 0.0)
        c = "#00ff88" if state else "#ff4444"
        self._onoff_lbl.setText("ON" if state else "OFF")
        self._onoff_lbl.setStyleSheet(f"color:{c};font-weight:bold;font-size:11px;")

    def update_read(self, sig_name, value):
        if sig_name in self._meters: self._meters[sig_name].setValue(value)

    def get_write_value(self, sig): return self._write_widgets[sig].value() if sig in self._write_widgets else 0.0
    def get_nmt_value(self):   return 1 if self._nmt_state   else 2
    def get_onoff_value(self): return 1.0 if self._onoff_state else 0.0
    def get_all_write_values(self): return {sig: sb.value() for sig, sb in self._write_widgets.items()}


# ═══════════════════════════════════════════════════════════════════════════════
#  DUT Section Widget
# ═══════════════════════════════════════════════════════════════════════════════
class DUTSection(QGroupBox):
    diag_send_requested = pyqtSignal(bytes)

    def __init__(self, parent=None):
        super().__init__("DUT  –  Vehicle DCDC Converter  [CH3 / CAN1]", parent)
        self._write_widgets = {}
        self._opmode_val    = 0
        self._build()

    def _build(self):
        main = QVBoxLayout(self); main.setSpacing(6)

        # Meters
        m_grp = QGroupBox("Live Readings")
        m_lay = QHBoxLayout(m_grp); m_lay.setSpacing(6)
        self._meter_volt = AnalogMeter("MV VOLTAGE", "V",  0, 100)
        self._meter_curr = AnalogMeter("MV CURRENT", "A",  0, 100)
        self._meter_12v  = AnalogMeter("12V VOLTAGE","V",  0,  20)
        self._meter_12a  = AnalogMeter("12V CURRENT","A",  0,  50)
        for m in (self._meter_volt, self._meter_curr, self._meter_12v, self._meter_12a): m_lay.addWidget(m)
        extra = QVBoxLayout()
        self._opmode_lbl = QLabel("OpMode: ---"); self._opmode_lbl.setObjectName("readVal")
        extra.addWidget(self._opmode_lbl); extra.addStretch()
        m_lay.addLayout(extra)
        main.addWidget(m_grp)

        # OpMode radios
        op_grp = QGroupBox("DCDCOperatingModeReqEx")
        op_lay = QGridLayout(op_grp); op_lay.setSpacing(4)
        self._opmode_group = QButtonGroup(self)
        for i, (val, label) in enumerate(OPMODE_VALUES):
            rb = QRadioButton(f"{val}: {label}")
            if val == 0: rb.setChecked(True)
            self._opmode_group.addButton(rb, val)
            op_lay.addWidget(rb, i//2, i%2)
        self._opmode_group.buttonClicked.connect(lambda btn: setattr(self, '_opmode_val', self._opmode_group.id(btn)))
        main.addWidget(op_grp)

        # Write setpoints
        w_grp = QGroupBox("Write Setpoints")
        w_lay = QGridLayout(w_grp); w_lay.setSpacing(4)
        for row, (label, msg, sig, default, mn, mx, step, unit) in enumerate(DUT_WRITE_SIGNALS):
            w_lay.addWidget(QLabel(label), row, 0)
            sb = QDoubleSpinBox(); sb.setRange(mn, mx); sb.setSingleStep(step)
            sb.setDecimals(3); sb.setValue(default); sb.setMinimumWidth(100)
            self._write_widgets[sig] = sb
            w_lay.addWidget(sb, row, 1)
            w_lay.addWidget(QLabel(unit), row, 2)
        main.addWidget(w_grp)

        # Diagnostics
        diag_grp = QGroupBox("Diagnostics  (UDS / ISO 14229)")
        diag_lay = QVBoxLayout(diag_grp); diag_lay.setSpacing(6)

        # TX row
        tx_hdr = QLabel("TX  –  TST_PhysicalReqEPICD_PMZ"); tx_hdr.setStyleSheet("color:#ffdd00;font-size:10px;font-weight:bold;")
        diag_lay.addWidget(tx_hdr)
        tx_row = QHBoxLayout()
        self._diag_tx = DiagnosticsWidget()
        tx_row.addWidget(self._diag_tx)
        send_btn = QPushButton("Send Diag"); send_btn.setObjectName("diagBtn")
        send_btn.clicked.connect(self._send_diag_clicked)
        tx_row.addWidget(send_btn)
        clr_btn = QPushButton("Clear"); clr_btn.clicked.connect(self._diag_tx.clear)
        tx_row.addWidget(clr_btn)
        tx_row.addStretch()
        diag_lay.addLayout(tx_row)

        # RX row
        rx_hdr = QLabel("RX  –  TST_PhysicalRespEPICD_PMZ"); rx_hdr.setStyleSheet("color:#00ccff;font-size:10px;font-weight:bold;")
        diag_lay.addWidget(rx_hdr)
        rx_row = QHBoxLayout()
        self._diag_rx = HexDisplayWidget()
        rx_row.addWidget(self._diag_rx)
        clr_rx = QPushButton("Clear"); clr_rx.clicked.connect(self._diag_rx.clear)
        rx_row.addWidget(clr_rx)
        rx_row.addStretch()
        diag_lay.addLayout(rx_row)

        main.addWidget(diag_grp)

    def _send_diag_clicked(self):
        self.diag_send_requested.emit(self._diag_tx.get_bytes())

    def update_diag_response(self, data: bytes):
        self._diag_rx.set_bytes(data)

    def update_read(self, sig_name, value):
        m_map = {"DCDCVoltageMV": self._meter_volt, "DCDCCurrentMV": self._meter_curr,
                 "DCDC12vActualVoltage": self._meter_12v, "DCDC12vActualCurrent": self._meter_12a}
        if sig_name in m_map: m_map[sig_name].setValue(value)
        elif sig_name == "DCDCOperatingModeExt2":
            self._opmode_lbl.setText(f"OpMode: {dict(OPMODE_VALUES).get(int(value), str(value))}")

    def get_opmode_value(self): return self._opmode_val
    def get_all_write_values(self):
        v = {sig: sb.value() for sig, sb in self._write_widgets.items()}
        v["DCDCOperatingModeReqEx"] = float(self._opmode_val)
        return v


# ═══════════════════════════════════════════════════════════════════════════════
#  Log Tab  (read + write signals)
# ═══════════════════════════════════════════════════════════════════════════════
class LogTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._logging = False; self._logfile = None; self._writer = None
        self._enabled_sigs = {}; self._build()

    def _build(self):
        lay = QVBoxLayout(self)

        ctrl = QHBoxLayout()
        self._fname_lbl = QLabel("No file"); ctrl.addWidget(self._fname_lbl, 1)
        self._start_btn = QPushButton("▶  Start Logging"); self._start_btn.setObjectName("startBtn")
        self._start_btn.clicked.connect(self._start); ctrl.addWidget(self._start_btn)
        self._stop_btn  = QPushButton("■  Stop Logging");  self._stop_btn.setObjectName("stopBtn")
        self._stop_btn.setEnabled(False); self._stop_btn.clicked.connect(self._stop)
        ctrl.addWidget(self._stop_btn)
        lay.addLayout(ctrl)

        # Select / deselect all buttons
        sel_row = QHBoxLayout()
        sel_all = QPushButton("Select All");   sel_all.clicked.connect(lambda: self._set_all(True))
        desel   = QPushButton("Deselect All"); desel.clicked.connect(lambda: self._set_all(False))
        sel_row.addWidget(sel_all); sel_row.addWidget(desel); sel_row.addStretch()
        lay.addLayout(sel_row)

        chk_grp = QGroupBox("Select signals to log")
        chk_lay = QGridLayout(chk_grp); col = 0; row = 0

        all_sigs = []
        # Read signals
        for _, _, sig in PS_READ_SIGNALS:
            all_sigs.append((f"PS1_R_{sig}", f"PS1 read / {sig}"))
            all_sigs.append((f"PS2_R_{sig}", f"PS2 read / {sig}"))
        for _, _, sig in DUT_READ_SIGNALS:
            all_sigs.append((f"DUT_R_{sig}", f"DUT read / {sig}"))
        # Write signals
        for _, _, sig, *_ in PS_WRITE_SIGNALS:
            all_sigs.append((f"PS1_W_{sig}", f"PS1 write / {sig}"))
            all_sigs.append((f"PS2_W_{sig}", f"PS2 write / {sig}"))
        for _, _, sig, *_ in DUT_WRITE_SIGNALS:
            all_sigs.append((f"DUT_W_{sig}", f"DUT write / {sig}"))
        all_sigs.append(("DUT_W_DCDCOperatingModeReqEx", "DUT write / DCDCOperatingModeReqEx"))
        # Toggle states
        all_sigs.append(("PS1_W_NMT_CS",           "PS1 write / NMT_CS"))
        all_sigs.append(("PS2_W_NMT_CS",           "PS2 write / NMT_CS"))
        all_sigs.append(("PS1_W_SDO_Server_OnOff", "PS1 write / SDO_Server_OnOff"))
        all_sigs.append(("PS2_W_SDO_Server_OnOff", "PS2 write / SDO_Server_OnOff"))
        # Diag
        all_sigs.append(("DUT_DIAG_TX", "DUT Diag TX (hex)"))
        all_sigs.append(("DUT_DIAG_RX", "DUT Diag RX (hex)"))

        for key, label in all_sigs:
            cb = QCheckBox(label); cb.setChecked(True)
            self._enabled_sigs[key] = cb
            chk_lay.addWidget(cb, row, col)
            col += 1
            if col >= 4: col = 0; row += 1

        scroll = QScrollArea(); scroll.setWidget(chk_grp); scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(260); lay.addWidget(scroll)

        self._tail = QTextEdit(); self._tail.setReadOnly(True); self._tail.setMaximumHeight(220)
        lay.addWidget(QLabel("Live log tail:")); lay.addWidget(self._tail)

    def _set_all(self, state):
        for cb in self._enabled_sigs.values(): cb.setChecked(state)

    def _start(self):
        ts = datetime.now().strftime("%d%m%Y%H%S"); fname = f"DCDClog_{ts}.csv"
        self._logfile = open(fname, "w", newline="")
        headers = ["timestamp_ms"] + [k for k, cb in self._enabled_sigs.items() if cb.isChecked()]
        self._writer = csv.DictWriter(self._logfile, fieldnames=headers, extrasaction="ignore")
        self._writer.writeheader(); self._logging = True
        self._fname_lbl.setText(f"Logging → {fname}")
        self._start_btn.setEnabled(False); self._stop_btn.setEnabled(True)

    def _stop(self):
        self._logging = False
        if self._logfile: self._logfile.close()
        self._fname_lbl.setText("Logging stopped")
        self._start_btn.setEnabled(True); self._stop_btn.setEnabled(False)

    def log_row(self, data: dict):
        if not self._logging or self._writer is None: return
        row = {"timestamp_ms": int(time.time()*1000)}
        for k, cb in self._enabled_sigs.items():
            if cb.isChecked() and k in data: row[k] = data[k]
        self._writer.writerow(row)
        self._tail.append(str(row))
        doc = self._tail.document()
        if doc.blockCount() > 50:
            cursor = self._tail.textCursor(); cursor.movePosition(cursor.Start)
            cursor.select(cursor.BlockUnderCursor); cursor.removeSelectedText(); cursor.deleteChar()


# ═══════════════════════════════════════════════════════════════════════════════
#  Automation Tab
# ═══════════════════════════════════════════════════════════════════════════════
class AutomationTab(QWidget):
    execute_step = pyqtSignal(dict)
    def __init__(self, parent=None):
        super().__init__(parent)
        self._steps = []; self._running = False; self._step_idx = 0
        self._timer = QTimer(); self._timer.timeout.connect(self._tick); self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        file_row = QHBoxLayout()
        self._file_lbl = QLabel("No CSV loaded"); file_row.addWidget(self._file_lbl, 1)
        load_btn = QPushButton("📂 Load CSV"); load_btn.clicked.connect(self._load_csv)
        file_row.addWidget(load_btn); lay.addLayout(file_row)
        hint = QLabel("CSV format:  timestamp_ms , signal_key , value")
        hint.setWordWrap(True); hint.setStyleSheet("color:#4a6080;font-size:10px;"); lay.addWidget(hint)
        ctrl = QHBoxLayout()
        self._prog = QProgressBar(); ctrl.addWidget(self._prog, 1)
        self._run_btn = QPushButton("▶ Run"); self._run_btn.setObjectName("startBtn")
        self._run_btn.clicked.connect(self._run); ctrl.addWidget(self._run_btn)
        self._abort_btn = QPushButton("■ Abort"); self._abort_btn.setObjectName("stopBtn")
        self._abort_btn.setEnabled(False); self._abort_btn.clicked.connect(self._abort)
        ctrl.addWidget(self._abort_btn); lay.addLayout(ctrl)
        self._log = QTextEdit(); self._log.setReadOnly(True); lay.addWidget(self._log)

    def _load_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load CSV", "", "CSV (*.csv)")
        if not path: return
        self._steps = []
        with open(path) as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or row[0].startswith("#"): continue
                try: self._steps.append((int(row[0]), row[1].strip(), float(row[2])))
                except: pass
        self._file_lbl.setText(f"Loaded {len(self._steps)} steps")
        self._prog.setMaximum(len(self._steps)); self._prog.setValue(0)
        self._log.append(f"Loaded {len(self._steps)} steps.")

    def _run(self):
        if not self._steps: self._log.append("No steps."); return
        self._running = True; self._step_idx = 0
        self._start_ms = int(time.time()*1000)
        self._run_btn.setEnabled(False); self._abort_btn.setEnabled(True)
        self._timer.start(10); self._log.append("Automation started.")

    def _abort(self):
        self._running = False; self._timer.stop()
        self._run_btn.setEnabled(True); self._abort_btn.setEnabled(False)
        self._log.append("Aborted.")

    def _tick(self):
        if not self._running or self._step_idx >= len(self._steps):
            if self._step_idx >= len(self._steps): self._log.append("Complete.")
            self._abort(); return
        now_ms = int(time.time()*1000) - self._start_ms
        ts, key, val = self._steps[self._step_idx]
        if now_ms >= ts:
            self.execute_step.emit({key: val})
            self._log.append(f"t={ts}ms  {key} = {val}")
            self._prog.setValue(self._step_idx + 1)
            self._step_idx += 1


# ═══════════════════════════════════════════════════════════════════════════════
#  Status Bar
# ═══════════════════════════════════════════════════════════════════════════════
class StatusBar(QWidget):
    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self); lay.setContentsMargins(4,2,4,2)
        self._ch3 = QLabel("CH3/CAN1-DUT: ●"); self._ch3.setStyleSheet("color:#ff4444")
        self._ch4 = QLabel("CH4/CAN2-PS: ●");  self._ch4.setStyleSheet("color:#ff4444")
        self._tx  = QLabel("TX: –")
        lay.addWidget(self._ch3); lay.addWidget(self._ch4); lay.addWidget(self._tx, 1)

    def set_connected(self, ch, ok):
        lbl = self._ch3 if ch == 3 else self._ch4
        lbl.setStyleSheet(f"color:{'#00ff88' if ok else '#ff4444'}")
    def set_tx(self, text): self._tx.setText(f"TX: {text}")


# ═══════════════════════════════════════════════════════════════════════════════
#  Main Window
# ═══════════════════════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CAN GUI  –  VN1640A  |  CH3→DUT  CH4→PS1+PS2")
        self.resize(1440, 920); self.setStyleSheet(DARK_SS)
        self.db_ps1 = None; self.db_ps2 = None; self.db_dut = None
        if HW_AVAILABLE:
            try:
                self.db_ps1 = cantools.database.load_file(str(PS1_DBC), encoding="latin-1")
                self.db_ps2 = cantools.database.load_file(str(PS2_DBC), encoding="latin-1")
                self.db_dut = cantools.database.load_file(str(DUT_DBC), encoding="latin-1")
            except Exception as e: print(f"DBC load error: {e}")

        self._worker_thread = QThread()
        self._worker = CANWorker(self.db_ps1, self.db_ps2, self.db_dut)
        self._worker.moveToThread(self._worker_thread)
        self._worker.rx_data.connect(self._on_rx)
        self._worker.rx_diag.connect(self._on_diag_rx)
        self._worker.status.connect(lambda m: self.statusBar().showMessage(m, 5000))
        self._worker_thread.started.connect(self._worker.start_buses)
        self._worker_thread.start()
        self._rx_thread = threading.Thread(target=self._worker.receive_loop, daemon=True)
        self._rx_thread.start()

        self._live = {}

        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(6,6,6,4)
        self._status_bar = StatusBar(); root.addWidget(self._status_bar)
        self._tabs = QTabWidget(); root.addWidget(self._tabs)
        self._build_remote_tab(); self._build_log_tab(); self._build_auto_tab()

        self._tx_timer = QTimer(); self._tx_timer.timeout.connect(self._periodic_tx); self._tx_timer.start(15)
        self._ref_timer = QTimer(); self._ref_timer.timeout.connect(self._tick_log); self._ref_timer.start(200)

    def _build_remote_tab(self):
        tab = QWidget(); scroll = QScrollArea(); scroll.setWidget(tab); scroll.setWidgetResizable(True)
        self._tabs.addTab(scroll, "🎮  Remote Control")
        lay = QHBoxLayout(tab); lay.setSpacing(8)
        self._ps1 = PSSection("⚡  Power Supply 1  (IT6000 – CH4/CAN2)", 1)
        self._ps2 = PSSection("⚡  Power Supply 2  (IT6000 – CH4/CAN2)", 2)
        self._dut = DUTSection()
        self._ps1.values_changed.connect(self._handle_ps_change)
        self._ps2.values_changed.connect(self._handle_ps_change)
        self._dut.diag_send_requested.connect(self._send_diag)
        lay.addWidget(self._ps1, 1); lay.addWidget(self._ps2, 1); lay.addWidget(self._dut, 1)

    def _build_log_tab(self):
        self._log_tab = LogTab(); self._tabs.addTab(self._log_tab, "📋  Log")

    def _build_auto_tab(self):
        self._auto_tab = AutomationTab()
        self._auto_tab.execute_step.connect(self._execute_auto_step)
        self._tabs.addTab(self._auto_tab, "🤖  Automation")

    def _periodic_tx(self):
        if self.db_ps1 is None or self.db_ps2 is None: return
        # PS1 on CH4
        self._worker.send_nmt(1, self._ps1.get_nmt_value())
        self._worker.send_rpdo1(1, self.db_ps1, self._ps1.get_write_value("dc_mode"), self._ps1.get_write_value("dc_voltage"))
        self._worker.send_rpdo2(1, self.db_ps1, self._ps1.get_write_value("dc_current"))
        # PS2 on CH4
        self._worker.send_nmt(2, self._ps2.get_nmt_value())
        self._worker.send_rpdo1(2, self.db_ps2, self._ps2.get_write_value("dc_mode"), self._ps2.get_write_value("dc_voltage"))
        self._worker.send_rpdo2(2, self.db_ps2, self._ps2.get_write_value("dc_current"))
        # DUT on CH3
        if self.db_dut:
            dv = self._dut.get_all_write_values()
            self._worker.send_dut("PCM_PMZ_DCDCControl", {
                "DCDCOperatingModeReqEx": float(self._dut.get_opmode_value()),
                "DCDCVoltageMVRequest": dv.get("DCDCVoltageMVRequest", 0),
                "DCDCCurrentMVLimit":   dv.get("DCDCCurrentMVLimit",   0),
            })
            self._worker.send_dut("GWM_PMZ_CoreSystem",  {"DCDC12vSetpointRequest": dv.get("DCDC12vSetpointRequest", 0)})
            self._worker.send_dut("RCM_FR_PR_GW_1_PMZ",  {"CrashStatusRCM": dv.get("CrashStatusRCM", 0)})
            self._worker.send_dut("BCM_PMZ_Core",         {"PowerMode": dv.get("PowerMode", 0)})
        # Update live dict with write values
        for sig, val in self._ps1.get_all_write_values().items():
            self._live[f"PS1_W_{sig}"] = val
        for sig, val in self._ps2.get_all_write_values().items():
            self._live[f"PS2_W_{sig}"] = val
        for sig, val in self._dut.get_all_write_values().items():
            self._live[f"DUT_W_{sig}"] = val
        self._live["PS1_W_NMT_CS"]           = float(self._ps1.get_nmt_value())
        self._live["PS2_W_NMT_CS"]           = float(self._ps2.get_nmt_value())
        self._live["PS1_W_SDO_Server_OnOff"] = self._ps1.get_onoff_value()
        self._live["PS2_W_SDO_Server_OnOff"] = self._ps2.get_onoff_value()

    def _send_diag(self, raw_bytes: bytes):
        self._worker.send_diag_request(raw_bytes)
        self._live["DUT_DIAG_TX"] = raw_bytes.hex(' ').upper()
        self._status_bar.set_tx(f"DiagTX: {raw_bytes.hex(' ').upper()}")

    def _on_diag_rx(self, data: bytes):
        self._dut.update_diag_response(data)
        self._live["DUT_DIAG_RX"] = data.hex(' ').upper()

    def _handle_ps_change(self, ps_idx, frame_key, signal_name, value):
        self._live[f"PS{ps_idx}_W_{signal_name}"] = value
        self._status_bar.set_tx(f"PS{ps_idx} {signal_name}={value}")

    def _on_rx(self, data: dict):
        for frame_name, signals in data.items():
            for sig, val in signals.items():
                if frame_name in ("TPDO_1", "TPDO1", "TPDO1_PS1", "TPDO1_PS2"):
                    self._ps1.update_read(sig, float(val)); self._ps2.update_read(sig, float(val))
                    self._live[f"PS1_R_{sig}"] = float(val); self._live[f"PS2_R_{sig}"] = float(val)
                elif frame_name in ("TPDO_2", "TPDO2") and "Meter_power" in signals:
                    v = float(signals["Meter_power"])
                    self._ps1.update_read("Meter_power", v); self._ps2.update_read("Meter_power", v)
                    self._live["PS1_R_Meter_power"] = v; self._live["PS2_R_Meter_power"] = v
                elif frame_name in ("DCDCOpModeMV", "HVDCDC_PMZ_12v"):
                    for s, v in signals.items():
                        self._dut.update_read(s, float(v)); self._live[f"DUT_R_{s}"] = float(v)

    def _tick_log(self): self._log_tab.log_row(self._live)

    def _execute_auto_step(self, step: dict):
        for key, val in step.items():
            parts = key.split("_", 1)
            if len(parts) < 2: continue
            prefix, rest = parts[0], parts[1]
            if prefix in ("PS1", "PS2"):
                ps = self._ps1 if prefix == "PS1" else self._ps2
                if rest == "NMT_CS":           ps._nmt_toggle.setState(val == 1)
                elif rest == "SDO_Server_OnOff": ps._onoff_toggle.setState(val == 1)
                elif rest in ps._write_widgets:  ps._write_widgets[rest].setValue(val)
            elif prefix == "DUT":
                if rest == "DCDCOperatingModeReqEx":
                    btn = self._dut._opmode_group.button(int(val))
                    if btn: btn.setChecked(True); self._dut._opmode_val = int(val)
                elif rest in self._dut._write_widgets:
                    self._dut._write_widgets[rest].setValue(val)

    def closeEvent(self, event):
        self._tx_timer.stop(); self._worker.stop_buses()
        self._worker_thread.quit(); self._worker_thread.wait(2000); super().closeEvent(event)


def main():
    app = QApplication(sys.argv); win = MainWindow(); win.show(); sys.exit(app.exec_())

if __name__ == "__main__":
    main()
