"""
Serial console viewer for router boot logs (e.g. Netgear WNR3500L v2) on Windows.

Install:   pip install pyserial
Usage:     python router_serial.py                 (pick port from a list)
           python router_serial.py -p COM5         (specify port)
           python router_serial.py -p COM5 -b 115200 -l bootlog.txt

Keyboard input is forwarded to the router, so you can interrupt the
bootloader (CFE: Ctrl+C during the first seconds) or log in once booted.
Exit with Ctrl+] (it is not sent to the device).
"""

import argparse
import msvcrt
import sys
import threading
import time
from datetime import datetime

import serial
import serial.tools.list_ports


def pick_port():
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        sys.exit("No serial ports found. Check the adapter/driver (CH340, CP210x, FTDI, PL2303).")
    print("Available ports:")
    for i, p in enumerate(ports):
        print(f"  [{i}] {p.device} - {p.description}")
    choice = input("Select port number: ").strip()
    try:
        return ports[int(choice)].device
    except (ValueError, IndexError):
        sys.exit("Invalid selection.")


def keyboard_thread(ser, stop):
    """Forward keystrokes to the serial port. Ctrl+] (0x1d) quits."""
    while not stop.is_set():
        if not msvcrt.kbhit():
            time.sleep(0.01)
            continue
        ch = msvcrt.getwch()
        if ch == "\x1d":  # Ctrl+]
            stop.set()
            break
        if ch in ("\x00", "\xe0"):  # special key prefix (arrows, F-keys)
            msvcrt.getwch()  # discard second code
            continue
        if ch == "\r":
            ch = "\r\n" if False else "\r"  # most consoles want just CR
        try:
            ser.write(ch.encode("utf-8", errors="ignore"))
        except serial.SerialException:
            stop.set()


def main():
    ap = argparse.ArgumentParser(description="Router serial console viewer")
    ap.add_argument("-p", "--port", help="COM port, e.g. COM5")
    ap.add_argument("-b", "--baud", type=int, default=115200, help="baud rate (default 115200)")
    ap.add_argument("-l", "--log", help="also save output to this file")
    ap.add_argument("-t", "--timestamps", action="store_true", help="timestamp each line in the log file")
    args = ap.parse_args()

    port = args.port or pick_port()

    try:
        ser = serial.Serial(port, args.baud, bytesize=8, parity="N", stopbits=1,
                            timeout=0.1, xonxoff=False, rtscts=False, dsrdtr=False)
    except serial.SerialException as e:
        sys.exit(f"Could not open {port}: {e}")

    logf = open(args.log, "a", encoding="utf-8", errors="replace") if args.log else None
    print(f"--- Connected to {port} @ {args.baud} 8N1. Ctrl+] to exit. Power on the router now. ---")

    stop = threading.Event()
    threading.Thread(target=keyboard_thread, args=(ser, stop), daemon=True).start()

    at_line_start = True
    try:
        while not stop.is_set():
            data = ser.read(1024)
            if not data:
                continue
            text = data.decode("utf-8", errors="replace")
            sys.stdout.write(text)
            sys.stdout.flush()
            if logf:
                if args.timestamps:
                    out = []
                    for c in text:
                        if at_line_start and c not in "\r\n":
                            out.append(datetime.now().strftime("[%H:%M:%S.%f")[:-3] + "] ")
                            at_line_start = False
                        out.append(c)
                        if c == "\n":
                            at_line_start = True
                    logf.write("".join(out))
                else:
                    logf.write(text)
                logf.flush()
    except serial.SerialException as e:
        print(f"\n--- Serial error: {e} ---")
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        ser.close()
        if logf:
            logf.close()
        print("\n--- Disconnected ---")


if __name__ == "__main__":
    main()