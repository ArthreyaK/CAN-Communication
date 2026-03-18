"""
Vector XL Channel Finder
========================
Run this script BEFORE using can_gui_hw.py to discover:
  - Which xl channel indices are available
  - Which app_name to use
  - Bitrate detected on each channel

Usage:
    python find_vector_channels.py

No CANoe or hardware config changes needed.
"""

import sys

# ── Check python-can is installed ────────────────────────────────────────────
try:
    import can
    from can.interfaces.vector import VectorBus
    from can.interfaces.vector import xldefine, xlclass
except ImportError:
    print("\n  ERROR: python-can not installed.")
    print("  Run:  pip install python-can\n")
    sys.exit(1)

# ── App names to try (in priority order) ─────────────────────────────────────
# CANoe registers channels under "CANoe". If you used CANoe before,
# this is almost certainly the correct one.
APP_NAMES_TO_TRY = [
    "CANoe",       # ← most likely since you used CANoe
    "CANalyzer",
    "Python",
    "CAPL",
    "Vector",
    "",            # blank = let driver pick
]

BITRATES_TO_TRY = [500000, 250000, 1000000, 125000]

SEP = "─" * 62

def try_open(channel_idx, app_name, bitrate):
    try:
        b = can.interface.Bus(
            bustype="vector",
            channel=channel_idx,
            bitrate=bitrate,
            app_name=app_name,
            fd=False,
        )
        b.shutdown()
        return True, None
    except Exception as e:
        return False, str(e)

def probe_xl_driver():
    """Use the XL driver API directly to list all channels without opening them."""
    print(f"\n{'═'*62}")
    print("  STEP 1 — Query Vector XL Driver for installed hardware")
    print(f"{'═'*62}")
    try:
        # VectorBus exposes the xl driver handle
        import ctypes
        from can.interfaces.vector.xldriver import xlGetDriverConfig
        from can.interfaces.vector.xlclass import XLdriverConfig

        config = XLdriverConfig()
        # Try to call xlGetDriverConfig via the loaded dll
        dll = can.interfaces.vector.xldriver.xldriver
        result = dll.xlGetDriverConfig(ctypes.byref(config))
        if result != 0:
            print(f"  xlGetDriverConfig returned error code: {result}")
            return []

        channels = []
        print(f"\n  Found {config.channelCount} channel(s) in XL driver:\n")
        print(f"  {'Idx':>4}  {'Name':<28}  {'HW Type':<18}  {'Serial':<10}  {'Active Apps'}")
        print(f"  {SEP}")
        for i in range(config.channelCount):
            ch = config.channel[i]
            name        = ch.name.decode("latin-1", errors="replace").strip()
            hw_type     = ch.transceiverName.decode("latin-1", errors="replace").strip()
            serial      = ch.serialNumber
            active_apps = getattr(ch, 'applicationName', b'').decode("latin-1", errors="replace").strip()
            print(f"  {i:>4}  {name:<28}  {hw_type:<18}  {serial:<10}  {active_apps}")
            channels.append((i, name, hw_type, serial, active_apps))
        return channels

    except Exception as e:
        print(f"  Could not query XL driver directly: {e}")
        print("  (This is OK – falling back to brute-force probe)\n")
        return []


def brute_force_probe():
    print(f"\n{'═'*62}")
    print("  STEP 2 — Brute-force open probe  (indices 0–7 × app names)")
    print(f"{'═'*62}")
    print("  This tries every combination and reports what opens.\n")

    working = []   # list of (idx, app_name, bitrate)

    for idx in range(8):
        print(f"\n  ── xl index {idx}  (Physical CH{idx+1}) ──────────────────────")
        found_any = False
        for app in APP_NAMES_TO_TRY:
            ok, err = try_open(idx, app, 500000)   # use 500k for probe
            if ok:
                print(f"    ✓  app_name='{app}'  bitrate=500000  →  OPENED OK")
                working.append((idx, app, 500000))
                found_any = True
                # Don't break – show all working app names for this index
            else:
                # Classify the error to give useful feedback
                e_low = err.lower()
                if any(x in e_low for x in ["not found", "no channel", "invalid channel",
                                              "channel not", "does not exist"]):
                    print(f"    ✗  app_name='{app}'  →  channel not present")
                    break   # no point trying more app names if channel absent
                elif "access" in e_low or "in use" in e_low or "already" in e_low:
                    print(f"    ✗  app_name='{app}'  →  ACCESS DENIED (try a different app_name)")
                elif "permission" in e_low:
                    print(f"    ✗  app_name='{app}'  →  permission error")
                else:
                    # Truncate long errors
                    short = err[:80].replace('\n', ' ')
                    print(f"    ✗  app_name='{app}'  →  {short}")

        if not found_any:
            print(f"    (no app_name worked for index {idx})")

    return working


def print_summary(working):
    print(f"\n{'═'*62}")
    print("  SUMMARY — Copy these values into can_gui_hw.py")
    print(f"{'═'*62}\n")

    if not working:
        print("  ✗  No channels could be opened.\n")
        print("  Possible reasons:")
        print("    1. CANoe is still running and holding the channels exclusively.")
        print("       → Close CANoe completely and re-run this script.")
        print("    2. The Vector XL driver is not installed.")
        print("       → Install Vector Driver Setup from vector.com")
        print("    3. The VN1640A is not powered / connected via USB.")
        print("    4. The app registration in Vector Hardware Config needs updating.")
        print("       → Open 'Vector Hardware Config', select your channels,")
        print("         set Application to 'Python' or any free slot, click OK.\n")
        return

    print("  ✓  Working channels found:\n")

    # Group by app_name
    by_app = {}
    for idx, app, br in working:
        by_app.setdefault(app, []).append(idx)

    for app, indices in by_app.items():
        print(f"    app_name = \"{app}\"")
        for idx in indices:
            print(f"      xl index {idx}  →  Physical CH{idx+1}")

    print()

    # Give specific recommendation for VN1640A (2 CAN + 2 LIN)
    can_indices = [idx for idx, app, br in working]
    if len(can_indices) >= 2:
        # VN1640A: CH1,CH2=LIN, CH3,CH4=CAN  →  xl indices 2 and 3
        # But probe tells us the truth – use whatever actually opened
        best_app = working[0][1]
        print(f"  Recommended settings for can_gui_hw.py (top of file):\n")
        print(f"    CH_DUT      = {can_indices[0]}   # Physical CH{can_indices[0]+1} → DUT")
        if len(can_indices) > 1:
            print(f"    CH_PS       = {can_indices[1]}   # Physical CH{can_indices[1]+1} → PS1 + PS2")
        print(f"    VECTOR_APP_NAME = \"{best_app}\"")
    else:
        idx, app, br = working[0]
        print(f"  Only one channel found:")
        print(f"    CH_DUT or CH_PS = {idx}")
        print(f"    VECTOR_APP_NAME = \"{app}\"")

    print(f"\n{'═'*62}\n")


def main():
    print(f"\n{'═'*62}")
    print("  Vector XL Channel Finder")
    print("  for use with VN1640A / python-can")
    print(f"{'═'*62}")
    print(f"\n  python-can version : {can.__version__}")
    print(f"  Checking for Vector XL driver…")

    # Step 1: Try native XL driver query (gives rich info without opening)
    probe_xl_driver()

    # Step 2: Brute-force open probe (definitive – tells you what python-can can actually use)
    working = brute_force_probe()

    # Step 3: Print copy-paste summary
    print_summary(working)

    input("  Press Enter to exit…")


if __name__ == "__main__":
    main()
