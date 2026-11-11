# Project: Fingerprinting Electronic Control Units for Vehicle Intrusion Detection

This repo contains the code corresponding to the CPS project. It contains the code for each of the Microcontrollers.
The following hardware was used:
- 3 CH340G Dev boards (Arduino Uno Clones)
- 3 MCP2515 Can-Shields
- Breadboards and wires

The programming was done in VS Code using the PlatformIO extension.

To flash the firmware onto the boards, use i.e.

```pio run -e attackSuspend -t upload```

The "attackSuspend" refers to the environment within the *platformio.ini* file, where the target part should also be set. After flashing all the necessary firmware, run

```python logger.py COMy capture.csv``` to capture the traffic on the specified port and use ```python analyze.py capture.csv``` to run the analysis.