CAN Communication Suite – VN1640A
Quick-start guide
1.  Install dependencies
```
pip install python-can cantools PyQt5
```
> `cantools` handles all DBC parsing and signal encode/decode automatically.  
> `python-can` with the **Vector XL driver** backend talks to the VN1640A.
---
2.  Place your DBC files
File name	Purpose
`dut.dbc`	CAN1 / Channel 3 – DUT
`ps.dbc`	CAN2 / Channel 4 – Power Supplies
Put them in the same folder as `can_gui.py`, or edit `DBC_DUT_PATH` / `DBC_PS_PATH` at the top of the script.
---
3.  Configure signal names
Open `can_gui.py` and edit the USER-EDITABLE PARAMETERS block at the top:
Constant	What to change
`DUT_WRITE_SIGNALS`	7 write signal names + ranges (last field `True` = Diag button)
`DUT_READ_SIGNALS`	7 read signal names; type `"voltage"` / `"current"` → analog meter
`PS_WRITE_SIGNALS`	13 write signal name suffixes per PS
`PS_READ_SIGNALS`	3 read signal suffixes per PS
`PS1_PREFIX`	DBC prefix for PS1 signals (e.g. `"PS1_"`)
`PS2_PREFIX`	DBC prefix for PS2 signals (e.g. `"PS2_"`)
`DIAG_DISPLAY_DURATION`	Seconds the diagnostic response frame stays visible
---
4.  Run
```
python can_gui.py
```
---
5.  Hardware mapping
GUI	VN1640A physical channel
CAN1	Channel 3
CAN2	Channel 4
The script passes channel numbers 0-indexed to python-can:  
`channel 3 → index 2`,  `channel 4 → index 3`  
Adjust `CAN1_HW_CH` / `CAN2_HW_CH` if your hardware numbering differs.
---
6.  Automation CSV format
```csv
timestamp_ms,DUT_TargetVoltage,DUT_TargetCurrent,PS1_VoltageSetpoint
0,0.0,0.0,0.0
500,12.0,5.0,12.0
1000,24.0,10.0,24.0
2000,48.0,20.0,48.0
```
Column `timestamp_ms` is the elapsed time in milliseconds from Start.
Other column headers must exactly match the DBC signal names.
Press Initialise & Start – the script plays back rows at the correct timestamps.
---
7.  Logging
Go to the Logging tab.
Tick the signals you want to log (use the search box to filter).
Set an output `.csv` file path.
Click Start Logging – values are appended with a millisecond timestamp.
---
8.  Mock / offline mode
If a DBC file is not found the app starts in mock mode – the UI is fully functional but CAN sends are silently dropped and no signals are decoded. Useful for layout testing.
