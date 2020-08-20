"""

"""
import sys
import time
import logging
import numpy as np

import matplotlib as mpl
mpl.use('Qt5Agg') # disregard qtapp warning...
import matplotlib.pyplot as plt

import pypylon.pylon as pylon
import pypylon.genicam as geni

def draw_figure(num):
	mpl.rcParams['toolbar'] = 'None' 

	figure = plt.figure(num)
	ax = plt.axes([0,0,1,1], frameon=False)

	plt.axis('off')
	plt.autoscale(tight=True)
	plt.ion()

	imageWindow = ax.imshow(np.zeros((1,1,3), dtype='uint8'), 
		interpolation='none')

	figure.canvas.draw()
	plt.show(block=False)

	return figure, imageWindow

def DisplayFrames(c, dispQueue, ds, meta):
	if sys.platform == "win32" and meta['CameraMake'] == 'basler':
		imageWindow = pylon.PylonImageWindow()
		imageWindow.Create(c)
		imageWindow.Show()
		while(True):
			try:
				if dispQueue:
					grabResult = dispQueue.popleft()
					try:
						imageWindow.SetImage(grabResult)
						imageWindow.Show()
						grabResult.Release()
					except Exception as e:
						logging.error('Caught exception: {}'.format(e))
					except:
						grabResult.Release()
				else:
					time.sleep(0.01)
			except KeyboardInterrupt:
				break
		imageWindow.Close()
	else:
		figure, imageWindow = draw_figure(c+1)
		while(True):
			try:
				if dispQueue:
					img = dispQueue.popleft()
					try:
						imageWindow.set_data(img)
						figure.canvas.draw()
						figure.canvas.flush_events()
					except Exception as e:
						logging.error('Caught exception: {}'.format(e))
				else:
					time.sleep(0.01)
			except KeyboardInterrupt:
				break
		plt.close(figure)