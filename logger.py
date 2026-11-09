# pip install pyserial
import sys, time, serial

port = sys.argv[1]                       # e.g. COM7 or /dev/ttyUSB0
out  = sys.argv[2] if len(sys.argv) > 2 else "capture.csv"

with serial.Serial(port, 115200, timeout=1) as ser, open(out, "w") as f:
    ser.setDTR(False)                    # note: opening the port resets the Nano
    print(f"logging {port} -> {out}  (Ctrl+C to stop)")
    t0 = time.time()
    try:
        while True:
            line = ser.readline().decode(errors="ignore").strip()
            if not line or line.startswith("#") or line.startswith("id,"):
                continue
            f.write(line + "\n")
            if int(time.time() - t0) % 10 == 0:
                f.flush()
    except KeyboardInterrupt:
        pass
print("done")