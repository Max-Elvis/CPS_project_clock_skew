# Project: Fingerprinting Electronic Control Units for Vehicle Intrusion Detection

This repo contains the code corresponding to the CPS project. It contains the code for each of the microcontrollers.
The following hardware was used:
- 3 CH340G Dev boards (Arduino Nano Clones)
- 3 MCP2515 Can modules
- Breadboards and wires

The programming was done in VS Code using the PlatformIO extension.

To flash the firmware onto the boards, use i.e.

```pio run -e attackSuspend -t upload```

The "attackSuspend" refers to the environment within the *platformio.ini* file, where the target part should also be set. After flashing all the necessary firmware, run

```python logger.py COMy capture.csv``` to capture the traffic on the specified port and use ```python analyze.py capture.csv``` to run the analysis.

The folders prefixed with *src_bringup_* are mainly for testing purposes and basic CAN communication, while *src* contains the final code used on the boards to reproduce the results.
