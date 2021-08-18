"""
Module for Python Serial communication with Arduino microcontroller to control trigger rate
Compile campy/trigger/trigger_arduino.ino to operate
Inputs (from config.yaml -> params):
	frameRate: rate in frames/sec to trigger
	serialPort: COM port on PC for Arduino, e.g. 'COM3'
Currently rely on time delay to allow Arduino to initialize
TODO: Implement interactive communication link with Python and Arduino
E.g. Wait for 'Ready' message from Arduino to Python
"""

import serial
import time, logging


def StartTriggers(systems, params):
	try:
		systems["serial"] = serial.Serial(port=params["serialPort"], baudrate=115200, timeout=0.1)
		time.sleep(3)
		systems["serial"].write(str(params["frameRate"]).encode())
		print("Arduino on port {} is ready to trigger at {} fps."\
			.format(params["serialPort"],params["frameRate"]), flush=True)
	except Exception as e:
		pass
	return systems


def StopTriggers(systems):
	print("Closing serial connection...")
	systems["serial"].write(str(-1).encode())
	systems["serial"].close()
