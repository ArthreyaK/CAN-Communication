"""
CAN Communication GUI  –  SIMULATION Version  (No hardware required)
Sinusoidal random data injected.  CAN channel assignment mirrored from HW version:
  CH3 (CAN1) → DUT
  CH4 (CAN2) → PS1 + PS2
Requires:  PyQt5
Run:  python can_gui_sim.py
"""

import sys, csv, time, math, random
from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout,
    QHBoxLayout, QGridLayout, QLabel, QDoubleSpinBox, QPushButton,
    QGroupBox, QScrollArea, QFileDialog, QTextEdit, QCheckBox,
    QProgressBar, QButtonGroup, QRadioButton
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QRectF, QPointF
from PyQt5.QtGui import QFont, QPainter, QPen, QBrush, QRadialGradient, QFontMetrics, QColor
from PyQt5.QtWidgets import QLineEdit

OPMODE_VALUES = [
    (0, "Standby"), (1, "Buck Mode"), (2, "Reserved (Boost)"), (3, "Bus Discharge"),
    (4, "Bus Test Mode"), (5, "Not Used 5"), (6, "Not Used 6"), (7, "Not Used 7"),
]

PS_WRITE_SIGNALS = [
    ("dc_mode",             "RPDO1", "dc_mode",            0,  0,   1,    1,     "0=CV 1=CC"),
    ("dc_voltage (V)",      "RPDO1", "dc_voltage",         0,  0,  100,   0.001, "V"),
    ("dc_current (A)",      "RPDO2", "dc_current",         0, -100, 100,  0.001, "A"),
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

DUT_WRITE_SIGNALS = [
    ("DCDCVoltageMVRequest(V)", "PCM_PMZ_DCDCControl","DCDCVoltageMVRequest", 0,  0,    102.1,0.1,"V"),
    ("DCDCCurrentMVLimit(A)",   "PCM_PMZ_DCDCControl","DCDCCurrentMVLimit",   0,-102.35,102.35,0.1,"A"),
    ("DCDC12vSetpointRequest (V)",  "GWM_PMZ_CoreSystem", "DCDC12vSetpointRequest",0, 0,   25.3, 0.1,"V"),
    ("CrashStatusRCM",          "RCM_FR_PR_GW_1_PMZ","CrashStatusRCM",        0, 0,    1,    1,  "0=No 1=Crash"),
    ("PowerMode",               "BCM_PMZ_Core",       "PowerMode",             0, 0,   31,    1,  "0=KeyOut"),
]

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
QPushButton#diagBtn { background:#1a1a00; color:#ffdd00; border:1px solid #aaaa00; border-radius:4px; padding:5px 14px; font-size:11px; font-weight:bold; }
QPushButton#diagBtn:hover { background:#2a2a00; border-color:#ffff00; }
QPushButton#startBtn { background:#0d3322; color:#00ff88; border:1px solid #00aa55; }
QPushButton#stopBtn  { background:#3a0d0d; color:#ff4444; border:1px solid #aa2222; }
QDoubleSpinBox, QSpinBox, QComboBox, QLineEdit { background:#0d1117; color:#c8d8f0; border:1px solid #2a4a7a; border-radius:3px; padding:3px 6px; font-family:Consolas; }
QDoubleSpinBox:focus, QLineEdit:focus { border-color:#00aaff; }
QLabel#readVal { color:#00ff88; font-weight:bold; font-size:12px; font-family:Consolas; }
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


class AnalogMeter(QWidget):
    def __init__(self, label, unit, min_val, max_val, parent=None):
        super().__init__(parent)
        self.label=label; self.unit=unit; self.min_val=min_val; self.max_val=max_val
        self._value=min_val; self.setMinimumSize(140,140); self.setMaximumSize(160,160)
    def setValue(self, v):
        self._value=max(self.min_val,min(self.max_val,v)); self.update()
    def paintEvent(self, event):
        w,h=self.width(),self.height(); cx,cy=w/2,h*0.54; radius=min(w,h)*0.42
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        g=QRadialGradient(cx,cy,radius); g.setColorAt(0,QColor("#1a1a2e")); g.setColorAt(1,QColor("#0d0d1a"))
        p.setBrush(QBrush(g)); p.setPen(QPen(QColor("#3a3a5c"),2))
        p.drawEllipse(QRectF(cx-radius,cy-radius,radius*2,radius*2))
        sa,span=220,280; ar=radius*0.82
        rect=QRectF(cx-ar,cy-ar,ar*2,ar*2)
        p.setPen(QPen(QColor("#2a2a4a"),5,Qt.SolidLine,Qt.RoundCap))
        p.drawArc(rect,int((180-sa)*16),int(-span*16))
        frac=max(0.0,min(1.0,(self._value-self.min_val)/max(1e-9,self.max_val-self.min_val)))
        r=int(frac*2*255) if frac<0.5 else 255; g2=220 if frac<0.5 else int((1-(frac-0.5)*2)*220)
        p.setPen(QPen(QColor(r,g2,40),5,Qt.SolidLine,Qt.RoundCap))
        p.drawArc(rect,int((180-sa)*16),int(-frac*span*16))
        for i in range(11):
            a=math.radians(sa-i*(span/10)); im=(i%2==0)
            to=radius*0.88; ti=radius*(0.74 if im else 0.80)
            p.setPen(QPen(QColor("#6060aa"),2 if im else 1))
            p.drawLine(QPointF(cx+to*math.cos(a),cy-to*math.sin(a)),QPointF(cx+ti*math.cos(a),cy-ti*math.sin(a)))
        na=math.radians(sa-frac*span); nl=radius*0.70
        p.setPen(QPen(QColor("#ff4444"),2.5,Qt.SolidLine,Qt.RoundCap))
        p.drawLine(QPointF(cx,cy),QPointF(cx+nl*math.cos(na),cy-nl*math.sin(na)))
        p.setBrush(QBrush(QColor("#ff4444"))); p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(cx-4,cy-4,8,8))
        p.setPen(QColor("#e0e8ff")); fnt=QFont("Consolas",10,QFont.Bold); p.setFont(fnt)
        vt=f"{self._value:.1f}"; fm=QFontMetrics(fnt); tw=fm.horizontalAdvance(vt)
        p.drawText(int(cx-tw/2),int(cy+radius*0.45),vt)
        p.setPen(QColor("#7080a0")); fnt2=QFont("Consolas",8); p.setFont(fnt2)
        fm2=QFontMetrics(fnt2); uw=fm2.horizontalAdvance(self.unit)
        p.drawText(int(cx-uw/2),int(cy+radius*0.62),self.unit)
        p.setPen(QColor("#8899cc")); fnt3=QFont("Consolas",7,QFont.Bold); p.setFont(fnt3)
        fm3=QFontMetrics(fnt3); lw=fm3.horizontalAdvance(self.label)
        p.drawText(int(cx-lw/2),int(cy-radius*0.55),self.label)


class ToggleSwitch(QWidget):
    toggled = pyqtSignal(bool)
    def __init__(self, label_on="ON", label_off="OFF", initial=False, parent=None):
        super().__init__(parent); self._state=initial; self._label_on=label_on; self._label_off=label_off
        self.setFixedSize(90,34); self.setCursor(Qt.PointingHandCursor)
    def isChecked(self): return self._state
    def setState(self, state, emit=True):
        if self._state!=state: self._state=state; self.update()
        if emit: self.toggled.emit(self._state)
    def mousePressEvent(self, e): self._state=not self._state; self.update(); self.toggled.emit(self._state)
    def paintEvent(self, event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w,h=self.width(),self.height(); r=h*0.45
        p.setBrush(QBrush(QColor("#1aaa55") if self._state else QColor("#c0392b"))); p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(0,(h-h*0.55)/2,w,h*0.55),r,r)
        kx=w-h*0.6-2 if self._state else 2
        p.setBrush(QBrush(QColor("#ffffff"))); p.drawEllipse(QRectF(kx,2,h-4,h-4))
        p.setPen(QColor("#ffffff")); fnt=QFont("Consolas",8,QFont.Bold); p.setFont(fnt)
        txt=self._label_on if self._state else self._label_off
        fm=QFontMetrics(fnt); tw=fm.horizontalAdvance(txt)
        p.drawText(int(5 if self._state else w-tw-5),int(h*0.68),txt)


class HexByteEntry(QLineEdit):
    next_focus=pyqtSignal(); prev_focus=pyqtSignal()
    def __init__(self):
        super().__init__(); self.setMaxLength(2); self.setFixedWidth(30); self.setAlignment(Qt.AlignCenter)
        self.setPlaceholderText("00")
        self.setStyleSheet("background:#0d1117;color:#00ff88;border:1px solid #3a5a8a;border-radius:3px;font-family:Consolas;font-size:13px;font-weight:bold;")
        self.textChanged.connect(self._chg)
    def _chg(self, t):
        f=''.join(c for c in t.upper() if c in '0123456789ABCDEF')
        if f!=t.upper(): self.setText(f); return
        if len(f)==2: self.next_focus.emit()
    def keyPressEvent(self, e):
        if e.key()==Qt.Key_Backspace and len(self.text())==0: self.prev_focus.emit()
        super().keyPressEvent(e)
    def value_byte(self):
        t=self.text().strip()
        if not t: return 0
        return int(t,16) if all(c in '0123456789ABCDEFabcdef' for c in t) else 0


class DiagnosticsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay=QHBoxLayout(self); lay.setSpacing(4); lay.setContentsMargins(0,0,0,0)
        self._entries=[]
        for i in range(8):
            e=HexByteEntry(); self._entries.append(e); lay.addWidget(e)
            if i<7: sep=QLabel("·"); sep.setStyleSheet("color:#3a5a8a;font-size:14px;"); lay.addWidget(sep)
        for i,e in enumerate(self._entries):
            if i<7: e.next_focus.connect(self._entries[i+1].setFocus)
            if i>0: e.prev_focus.connect(self._entries[i-1].setFocus)
    def get_bytes(self): return bytes([e.value_byte() for e in self._entries])
    def clear(self):
        for e in self._entries: e.clear()


class HexDisplayWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay=QHBoxLayout(self); lay.setSpacing(4); lay.setContentsMargins(0,0,0,0)
        self._boxes=[]
        for i in range(8):
            b=QLineEdit("--"); b.setReadOnly(True); b.setFixedWidth(30); b.setAlignment(Qt.AlignCenter)
            b.setStyleSheet("background:#060a10;color:#00ccff;border:1px solid #1e3a5a;border-radius:3px;font-family:Consolas;font-size:13px;font-weight:bold;")
            self._boxes.append(b); lay.addWidget(b)
            if i<7: sep=QLabel("·"); sep.setStyleSheet("color:#1e3a5a;font-size:14px;"); lay.addWidget(sep)
    def set_bytes(self, data):
        for i,b in enumerate(data[:8]): self._boxes[i].setText(f"{b:02X}")
    def clear(self):
        for b in self._boxes: b.setText("--")


class PSSection(QGroupBox):
    def __init__(self, title, ps_idx, parent=None):
        super().__init__(title, parent)
        self.ps_idx=ps_idx; self._write_widgets={}; self._meters={}
        self._nmt_state=False; self._onoff_state=False; self._build()

    def _build(self):
        main=QVBoxLayout(self); main.setSpacing(6)
        m_grp=QGroupBox("Live Readings"); m_lay=QHBoxLayout(m_grp); m_lay.setSpacing(6)
        self._meter_volt=AnalogMeter("VOLTAGE","V",0,100)
        self._meter_curr=AnalogMeter("CURRENT","A",-100,100)
        self._meter_power=AnalogMeter("POWER","W",0,10000)
        for m in (self._meter_volt,self._meter_curr,self._meter_power): m_lay.addWidget(m)
        self._meters={"Meter_volt":self._meter_volt,"Meter_curr":self._meter_curr,"Meter_power":self._meter_power}
        main.addWidget(m_grp)

        ctrl_grp=QGroupBox("Control"); ctrl_lay=QHBoxLayout(ctrl_grp)
        ctrl_lay.addWidget(QLabel("NMT:"))
        self._nmt_toggle=ToggleSwitch("ON(1)","OFF(2)",initial=False)
        self._nmt_toggle.toggled.connect(self._nmt_changed); ctrl_lay.addWidget(self._nmt_toggle)
        self._nmt_lbl=QLabel("OFF"); self._nmt_lbl.setStyleSheet("color:#ff4444;font-weight:bold;font-size:11px;")
        ctrl_lay.addWidget(self._nmt_lbl); ctrl_lay.addSpacing(16)
        ctrl_lay.addWidget(QLabel("OnOff:"))
        self._onoff_toggle=ToggleSwitch("ON","OFF",initial=False)
        self._onoff_toggle.toggled.connect(self._onoff_changed); ctrl_lay.addWidget(self._onoff_toggle)
        self._onoff_lbl=QLabel("OFF"); self._onoff_lbl.setStyleSheet("color:#ff4444;font-weight:bold;font-size:11px;")
        ctrl_lay.addWidget(self._onoff_lbl); ctrl_lay.addStretch()
        main.addWidget(ctrl_grp)

        w_grp=QGroupBox("Write Setpoints"); w_lay=QGridLayout(w_grp); w_lay.setSpacing(4)
        for row,(label,fk,sig,default,mn,mx,step,unit) in enumerate(PS_WRITE_SIGNALS):
            w_lay.addWidget(QLabel(label),row,0)
            sb=QDoubleSpinBox(); sb.setRange(mn,mx); sb.setSingleStep(step); sb.setDecimals(3); sb.setValue(default); sb.setMinimumWidth(100)
            self._write_widgets[sig]=sb; w_lay.addWidget(sb,row,1); w_lay.addWidget(QLabel(unit),row,2)
        main.addWidget(w_grp)

    def _nmt_changed(self, state):
        self._nmt_state=state
        c="#00ff88" if state else "#ff4444"
        self._nmt_lbl.setText("ON" if state else "OFF"); self._nmt_lbl.setStyleSheet(f"color:{c};font-weight:bold;font-size:11px;")
    def _onoff_changed(self, state):
        self._onoff_state=state
        c="#00ff88" if state else "#ff4444"
        self._onoff_lbl.setText("ON" if state else "OFF"); self._onoff_lbl.setStyleSheet(f"color:{c};font-weight:bold;font-size:11px;")
    def update_read(self, sig_name, value):
        if sig_name in self._meters: self._meters[sig_name].setValue(value)
    def get_write_value(self, sig): return self._write_widgets[sig].value() if sig in self._write_widgets else 0.0
    def get_nmt_value(self): return 1 if self._nmt_state else 2
    def get_onoff_value(self): return 1.0 if self._onoff_state else 0.0
    def get_all_write_values(self): return {sig:sb.value() for sig,sb in self._write_widgets.items()}


class DUTSection(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("DUT  –  Vehicle DCDC Converter  [CH3 / CAN1]", parent)
        self._write_widgets={}; self._opmode_val=0; self._build()

    def _build(self):
        main=QVBoxLayout(self); main.setSpacing(6)
        m_grp=QGroupBox("Live Readings"); m_lay=QHBoxLayout(m_grp); m_lay.setSpacing(6)
        self._meter_volt=AnalogMeter("MV VOLTAGE","V",0,100)
        self._meter_curr=AnalogMeter("MV CURRENT","A",0,100)
        self._meter_12v=AnalogMeter("12V VOLTAGE","V",0,20)
        self._meter_12a=AnalogMeter("12V CURRENT","A",0,50)
        for m in (self._meter_volt,self._meter_curr,self._meter_12v,self._meter_12a): m_lay.addWidget(m)
        extra=QVBoxLayout(); self._opmode_lbl=QLabel("OpMode: ---"); self._opmode_lbl.setObjectName("readVal")
        extra.addWidget(self._opmode_lbl); extra.addStretch(); m_lay.addLayout(extra)
        main.addWidget(m_grp)

        op_grp=QGroupBox("DCDCOperatingModeReqEx"); op_lay=QGridLayout(op_grp); op_lay.setSpacing(4)
        self._opmode_group=QButtonGroup(self)
        for i,(val,label) in enumerate(OPMODE_VALUES):
            rb=QRadioButton(f"{val}: {label}")
            if val==0: rb.setChecked(True)
            self._opmode_group.addButton(rb,val); op_lay.addWidget(rb,i//2,i%2)
        self._opmode_group.buttonClicked.connect(lambda btn: setattr(self,'_opmode_val',self._opmode_group.id(btn)))
        main.addWidget(op_grp)

        w_grp=QGroupBox("Write Setpoints"); w_lay=QGridLayout(w_grp); w_lay.setSpacing(4)
        for row,(label,msg,sig,default,mn,mx,step,unit) in enumerate(DUT_WRITE_SIGNALS):
            w_lay.addWidget(QLabel(label),row,0)
            sb=QDoubleSpinBox(); sb.setRange(mn,mx); sb.setSingleStep(step); sb.setDecimals(3); sb.setValue(default); sb.setMinimumWidth(100)
            self._write_widgets[sig]=sb; w_lay.addWidget(sb,row,1); w_lay.addWidget(QLabel(unit),row,2)
        main.addWidget(w_grp)

        diag_grp=QGroupBox("Diagnostics  (UDS / ISO 14229)"); diag_lay=QVBoxLayout(diag_grp); diag_lay.setSpacing(6)
        tx_hdr=QLabel("TX  –  TST_PhysicalReqEPICD_PMZ"); tx_hdr.setStyleSheet("color:#ffdd00;font-size:10px;font-weight:bold;")
        diag_lay.addWidget(tx_hdr)
        tx_row=QHBoxLayout(); self._diag_tx=DiagnosticsWidget(); tx_row.addWidget(self._diag_tx)
        send_btn=QPushButton("Send Diag"); send_btn.setObjectName("diagBtn")
        send_btn.clicked.connect(self._sim_send_diag); tx_row.addWidget(send_btn)
        clr_btn=QPushButton("Clear"); clr_btn.clicked.connect(self._diag_tx.clear); tx_row.addWidget(clr_btn)
        tx_row.addStretch(); diag_lay.addLayout(tx_row)
        rx_hdr=QLabel("RX  –  TST_PhysicalRespEPICD_PMZ"); rx_hdr.setStyleSheet("color:#00ccff;font-size:10px;font-weight:bold;")
        diag_lay.addWidget(rx_hdr)
        rx_row=QHBoxLayout(); self._diag_rx=HexDisplayWidget(); rx_row.addWidget(self._diag_rx)
        clr_rx=QPushButton("Clear"); clr_rx.clicked.connect(self._diag_rx.clear); rx_row.addWidget(clr_rx)
        rx_row.addStretch(); diag_lay.addLayout(rx_row)
        main.addWidget(diag_grp)

    def _sim_send_diag(self):
        tx_bytes = self._diag_tx.get_bytes()
        # Simulate a positive response: first byte = tx[0]+0x40, rest echo
        resp = bytearray(8)
        if tx_bytes[0] != 0:
            resp[0] = tx_bytes[0] | 0x40
        else:
            resp[0] = 0x50
        resp[1] = tx_bytes[1] if len(tx_bytes) > 1 else 0
        for i in range(2, 8): resp[i] = random.randint(0, 0xFF)
        QTimer.singleShot(50, lambda: self._diag_rx.set_bytes(bytes(resp)))

    def update_read(self, sig_name, value):
        m_map={"DCDCVoltageMV":self._meter_volt,"DCDCCurrentMV":self._meter_curr,
               "DCDC12vActualVoltage":self._meter_12v,"DCDC12vActualCurrent":self._meter_12a}
        if sig_name in m_map: m_map[sig_name].setValue(value)
        elif sig_name=="DCDCOperatingModeExt2":
            self._opmode_lbl.setText(f"OpMode: {dict(OPMODE_VALUES).get(int(value),str(value))}")
    def get_opmode_value(self): return self._opmode_val
    def get_all_write_values(self):
        v={sig:sb.value() for sig,sb in self._write_widgets.items()}
        v["DCDCOperatingModeReqEx"]=float(self._opmode_val); return v


class LogTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._logging=False; self._logfile=None; self._writer=None
        self._enabled_sigs={}; self._build()

    def _build(self):
        lay=QVBoxLayout(self)
        ctrl=QHBoxLayout(); self._fname_lbl=QLabel("No file"); ctrl.addWidget(self._fname_lbl,1)
        self._start_btn=QPushButton("▶  Start Logging"); self._start_btn.setObjectName("startBtn")
        self._start_btn.clicked.connect(self._start); ctrl.addWidget(self._start_btn)
        self._stop_btn=QPushButton("■  Stop Logging"); self._stop_btn.setObjectName("stopBtn")
        self._stop_btn.setEnabled(False); self._stop_btn.clicked.connect(self._stop); ctrl.addWidget(self._stop_btn)
        lay.addLayout(ctrl)

        sel_row=QHBoxLayout()
        sel_all=QPushButton("Select All"); sel_all.clicked.connect(lambda: self._set_all(True))
        desel=QPushButton("Deselect All"); desel.clicked.connect(lambda: self._set_all(False))
        sel_row.addWidget(sel_all); sel_row.addWidget(desel); sel_row.addStretch()
        lay.addLayout(sel_row)

        chk_grp=QGroupBox("Select signals to log"); chk_lay=QGridLayout(chk_grp); col=0; row=0
        all_sigs=[]
        read_map=[("PS1_R_Meter_volt","PS1 read/Meter_volt"),("PS2_R_Meter_volt","PS2 read/Meter_volt"),
                  ("PS1_R_Meter_curr","PS1 read/Meter_curr"),("PS2_R_Meter_curr","PS2 read/Meter_curr"),
                  ("PS1_R_Meter_power","PS1 read/Meter_power"),("PS2_R_Meter_power","PS2 read/Meter_power"),
                  ("DUT_R_DCDCVoltageMV","DUT read/DCDCVoltageMV"),("DUT_R_DCDCCurrentMV","DUT read/DCDCCurrentMV"),
                  ("DUT_R_DCDC12vActualVoltage","DUT read/DCDC12vActualVoltage"),
                  ("DUT_R_DCDC12vActualCurrent","DUT read/DCDC12vActualCurrent"),
                  ("DUT_R_DCDCOperatingModeExt2","DUT read/DCDCOperatingModeExt2")]
        all_sigs.extend(read_map)
        for _,_,sig,*_ in PS_WRITE_SIGNALS:
            all_sigs.append((f"PS1_W_{sig}",f"PS1 write/{sig}")); all_sigs.append((f"PS2_W_{sig}",f"PS2 write/{sig}"))
        for _,_,sig,*_ in DUT_WRITE_SIGNALS:
            all_sigs.append((f"DUT_W_{sig}",f"DUT write/{sig}"))
        all_sigs.extend([("DUT_W_DCDCOperatingModeReqEx","DUT write/DCDCOperatingModeReqEx"),
                         ("PS1_W_NMT_CS","PS1 write/NMT_CS"),("PS2_W_NMT_CS","PS2 write/NMT_CS"),
                         ("PS1_W_SDO_Server_OnOff","PS1 write/SDO_Server_OnOff"),
                         ("PS2_W_SDO_Server_OnOff","PS2 write/SDO_Server_OnOff"),
                         ("DUT_DIAG_TX","DUT Diag TX (hex)"),("DUT_DIAG_RX","DUT Diag RX (hex)")])
        for key,label in all_sigs:
            cb=QCheckBox(label); cb.setChecked(True); self._enabled_sigs[key]=cb
            chk_lay.addWidget(cb,row,col); col+=1
            if col>=4: col=0; row+=1
        scroll=QScrollArea(); scroll.setWidget(chk_grp); scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(260); lay.addWidget(scroll)
        self._tail=QTextEdit(); self._tail.setReadOnly(True); self._tail.setMaximumHeight(220)
        lay.addWidget(QLabel("Live log tail:")); lay.addWidget(self._tail)

    def _set_all(self, state):
        for cb in self._enabled_sigs.values(): cb.setChecked(state)

    def _start(self):
        ts=datetime.now().strftime("%d%m%Y%H%S"); fname=f"DCDClog_sim_{ts}.csv"
        self._logfile=open(fname,"w",newline="")
        headers=["timestamp_ms"]+[k for k,cb in self._enabled_sigs.items() if cb.isChecked()]
        self._writer=csv.DictWriter(self._logfile,fieldnames=headers,extrasaction="ignore")
        self._writer.writeheader(); self._logging=True
        self._fname_lbl.setText(f"Logging → {fname}")
        self._start_btn.setEnabled(False); self._stop_btn.setEnabled(True)

    def _stop(self):
        self._logging=False
        if self._logfile: self._logfile.close()
        self._fname_lbl.setText("Logging stopped")
        self._start_btn.setEnabled(True); self._stop_btn.setEnabled(False)

    def log_row(self, data):
        if not self._logging or self._writer is None: return
        row={"timestamp_ms":int(time.time()*1000)}
        for k,cb in self._enabled_sigs.items():
            if cb.isChecked() and k in data: row[k]=data[k]
        self._writer.writerow(row)
        self._tail.append(str(row))
        doc=self._tail.document()
        if doc.blockCount()>50:
            cursor=self._tail.textCursor(); cursor.movePosition(cursor.Start)
            cursor.select(cursor.BlockUnderCursor); cursor.removeSelectedText(); cursor.deleteChar()


class AutomationTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._steps=[]; self._running=False; self._step_idx=0
        self._timer=QTimer(); self._timer.timeout.connect(self._tick); self._build()
    def _build(self):
        lay=QVBoxLayout(self)
        file_row=QHBoxLayout(); self._file_lbl=QLabel("No CSV loaded"); file_row.addWidget(self._file_lbl,1)
        load_btn=QPushButton("📂 Load CSV"); load_btn.clicked.connect(self._load_csv); file_row.addWidget(load_btn)
        lay.addLayout(file_row)
        hint=QLabel("CSV format:  timestamp_ms , signal_key , value")
        hint.setWordWrap(True); hint.setStyleSheet("color:#4a6080;font-size:10px;"); lay.addWidget(hint)
        ctrl=QHBoxLayout(); self._prog=QProgressBar(); ctrl.addWidget(self._prog,1)
        self._run_btn=QPushButton("▶ Run"); self._run_btn.setObjectName("startBtn")
        self._run_btn.clicked.connect(self._run); ctrl.addWidget(self._run_btn)
        self._abort_btn=QPushButton("■ Abort"); self._abort_btn.setObjectName("stopBtn")
        self._abort_btn.setEnabled(False); self._abort_btn.clicked.connect(self._abort); ctrl.addWidget(self._abort_btn)
        lay.addLayout(ctrl); self._log=QTextEdit(); self._log.setReadOnly(True); lay.addWidget(self._log)
    def _load_csv(self):
        path,_=QFileDialog.getOpenFileName(self,"Load CSV","","CSV (*.csv)")
        if not path: return
        self._steps=[]
        with open(path) as f:
            reader=csv.reader(f)
            for row in reader:
                if not row or row[0].startswith("#"): continue
                try: self._steps.append((int(row[0]),row[1].strip(),float(row[2])))
                except: pass
        self._file_lbl.setText(f"Loaded {len(self._steps)} steps")
        self._prog.setMaximum(len(self._steps)); self._prog.setValue(0)
        self._log.append(f"Loaded {len(self._steps)} steps.")
    def _run(self):
        if not self._steps: self._log.append("No steps."); return
        self._running=True; self._step_idx=0; self._start_ms=int(time.time()*1000)
        self._run_btn.setEnabled(False); self._abort_btn.setEnabled(True)
        self._timer.start(10); self._log.append("Started.")
    def _abort(self):
        self._running=False; self._timer.stop()
        self._run_btn.setEnabled(True); self._abort_btn.setEnabled(False); self._log.append("Aborted.")
    def _tick(self):
        if not self._running or self._step_idx>=len(self._steps):
            if self._step_idx>=len(self._steps): self._log.append("Complete.")
            self._abort(); return
        now_ms=int(time.time()*1000)-self._start_ms
        ts,key,val=self._steps[self._step_idx]
        if now_ms>=ts:
            self._log.append(f"t={ts}ms  {key}={val}")
            self._prog.setValue(self._step_idx+1); self._step_idx+=1


class StatusBar(QWidget):
    def __init__(self):
        super().__init__()
        lay=QHBoxLayout(self); lay.setContentsMargins(4,2,4,2)
        self._ch3=QLabel("CH3/CAN1-DUT: ● SIM"); self._ch3.setStyleSheet("color:#00ff88")
        self._ch4=QLabel("CH4/CAN2-PS: ● SIM");  self._ch4.setStyleSheet("color:#00ff88")
        self._tx=QLabel("TX: SIMULATED @ 15ms"); self._tx.setStyleSheet("color:#888888")
        lay.addWidget(self._ch3); lay.addWidget(self._ch4); lay.addWidget(self._tx,1)
        sim_lbl=QLabel("⚠ SIMULATION MODE"); sim_lbl.setStyleSheet("color:#ffaa00;font-weight:bold;font-size:11px;")
        lay.addWidget(sim_lbl)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CAN GUI  –  SIMULATION  |  CH3→DUT  CH4→PS1+PS2")
        self.resize(1440,920); self.setStyleSheet(DARK_SS)
        self._t=0.0; self._live={}

        central=QWidget(); self.setCentralWidget(central)
        root=QVBoxLayout(central); root.setContentsMargins(6,6,6,4)
        self._status_bar=StatusBar(); root.addWidget(self._status_bar)
        self._tabs=QTabWidget(); root.addWidget(self._tabs)
        self._build_remote_tab(); self._build_log_tab(); self._build_auto_tab()

        self._sim_timer=QTimer(); self._sim_timer.timeout.connect(self._inject); self._sim_timer.start(15)
        self._log_timer=QTimer(); self._log_timer.timeout.connect(lambda: self._log_tab.log_row(self._live)); self._log_timer.start(200)

    def _build_remote_tab(self):
        tab=QWidget(); scroll=QScrollArea(); scroll.setWidget(tab); scroll.setWidgetResizable(True)
        self._tabs.addTab(scroll,"🎮  Remote Control")
        lay=QHBoxLayout(tab); lay.setSpacing(8)
        self._ps1=PSSection("⚡  Power Supply 1  (IT6000 – CH4/CAN2)",1)
        self._ps2=PSSection("⚡  Power Supply 2  (IT6000 – CH4/CAN2)",2)
        self._dut=DUTSection()
        lay.addWidget(self._ps1,1); lay.addWidget(self._ps2,1); lay.addWidget(self._dut,1)

    def _build_log_tab(self): self._log_tab=LogTab(); self._tabs.addTab(self._log_tab,"📋  Log")
    def _build_auto_tab(self): self._auto_tab=AutomationTab(); self._tabs.addTab(self._auto_tab,"🤖  Automation")

    def _inject(self):
        self._t+=0.015
        v1=60+20*math.sin(self._t*0.4)+random.gauss(0,0.3)
        c1=40*math.sin(self._t*0.7+1.0)+random.gauss(0,0.2)
        p1=max(0,v1*abs(c1)+random.gauss(0,5))
        self._ps1.update_read("Meter_volt",v1); self._ps1.update_read("Meter_curr",c1); self._ps1.update_read("Meter_power",p1)
        self._live.update({"PS1_R_Meter_volt":v1,"PS1_R_Meter_curr":c1,"PS1_R_Meter_power":p1})
        v2=48+15*math.sin(self._t*0.3+0.5)+random.gauss(0,0.3)
        c2=-30*math.sin(self._t*0.5+2.0)+random.gauss(0,0.2)
        p2=max(0,v2*abs(c2)+random.gauss(0,4))
        self._ps2.update_read("Meter_volt",v2); self._ps2.update_read("Meter_curr",c2); self._ps2.update_read("Meter_power",p2)
        self._live.update({"PS2_R_Meter_volt":v2,"PS2_R_Meter_curr":c2,"PS2_R_Meter_power":p2})
        dmv=48+8*math.sin(self._t*0.2)+random.gauss(0,0.2)
        cmi=20+10*math.sin(self._t*0.6+0.3)+random.gauss(0,0.1)
        v12=12.5+0.8*math.sin(self._t*0.15)+random.gauss(0,0.05)
        c12=8+5*math.sin(self._t*0.4)+random.gauss(0,0.1)
        self._dut.update_read("DCDCVoltageMV",dmv); self._dut.update_read("DCDCCurrentMV",cmi)
        self._dut.update_read("DCDC12vActualVoltage",v12); self._dut.update_read("DCDC12vActualCurrent",c12)
        self._dut.update_read("DCDCOperatingModeExt2",1)
        self._live.update({"DUT_R_DCDCVoltageMV":dmv,"DUT_R_DCDCCurrentMV":cmi,
                           "DUT_R_DCDC12vActualVoltage":v12,"DUT_R_DCDC12vActualCurrent":c12,
                           "DUT_R_DCDCOperatingModeExt2":1})
        # Write values
        for sig,val in self._ps1.get_all_write_values().items(): self._live[f"PS1_W_{sig}"]=val
        for sig,val in self._ps2.get_all_write_values().items(): self._live[f"PS2_W_{sig}"]=val
        for sig,val in self._dut.get_all_write_values().items(): self._live[f"DUT_W_{sig}"]=val
        self._live["PS1_W_NMT_CS"]=float(self._ps1.get_nmt_value())
        self._live["PS2_W_NMT_CS"]=float(self._ps2.get_nmt_value())
        self._live["PS1_W_SDO_Server_OnOff"]=self._ps1.get_onoff_value()
        self._live["PS2_W_SDO_Server_OnOff"]=self._ps2.get_onoff_value()


def main():
    app=QApplication(sys.argv); win=MainWindow(); win.show(); sys.exit(app.exec_())

if __name__=="__main__":
    main()
