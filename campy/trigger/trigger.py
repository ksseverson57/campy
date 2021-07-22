"""
Trigger nexus
"""

import logging

def ImportTrigger(params):
	if params["triggerController"] == "Arduino" or params["triggerController"] == "arduino":
		import campy.trigger.arduino as trigger
	elif params["triggerController"] == "None" or params["triggerController"] == "none":
		import campy.trigger.arduino as trigger
	else:
		print('The microcontroller you have selected is not supported.')
	return trigger


def StartTriggers(params):
	if params["startArduino"]:
		if params["triggerController"] != "None":
			trigger = ImportTrigger(params)
			params = trigger.StartTriggers(params)
	return params


def StopTriggers(params):
	if params["startArduino"]:
		if params["triggerController"] != "None":
			trigger = ImportTrigger(params)
			trigger.StopTriggers(params)