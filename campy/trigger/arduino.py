"""
Module for Python Serial communication with Arduino microcontroller to control trigger rate
Compile campy/trigger/trigger_arduino.ino to operate
Inputs (from config.yaml -> params):
	frameRate: rate in frames/sec to trigger
	serialPort: COM port on PC for Arduino, e.g. 'COM3'
Currently rely on time delay to allow Arduino to initialize
TODO: Implement interactive communication link with Python and Arduino
E.g. Wait for 'Ready' message from Arduino to Python instead of "dumb" sleep
"""

import serial
import time, logging


def StartTriggers(systems, params):
	try:
		# Open serial connection
		systems["serial"] = serial.Serial(\
							port=params["serialPort"],
							baudrate=115200,
							timeout=0.1)

		# This sleep is important. Wait for Arduino to initialize
		time.sleep(3)

		# Serialize pin length, IDs, and frame rate to a single string
		serialList = [len(params["digitalPins"])] + params["digitalPins"] + [params["frameRate"]]
		systems["serialCommand"] = serialList
		serialString = ",".join(str(item) for item in serialList)

		# Send command string
		systems["serial"].write(serialString.encode())

		print("Arduino on port {} is ready to trigger pins {} at {} fps."\
			.format(params["serialPort"], params["digitalPins"], params["frameRate"]), flush=True)

	except Exception as e:
		pass
	return systems


def StopTriggers(systems):
	print("Closing serial connection...")

	# Repeat the same Pyserial command, except encode frame rate as "-1"
	serialList = systems["serialCommand"]
	serialList[-1] = -1
	serialString = ",".join(str(item) for item in serialList)

	# Send command and close connection
	systems["serial"].write(serialString.encode())
	systems["serial"].close()


def ReceiveReadySignal(systems, params):

	return readySignal
