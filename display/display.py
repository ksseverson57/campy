"""

"""

import time
import numpy as np
import matplotlib as mpl
mpl.use('Qt5Agg') # disregard qtapp warning...
import matplotlib.pyplot as plt

def draw_figure(num):
    mpl.rcParams['toolbar'] = 'None' 

    figure = plt.figure(num)
    ax = plt.axes([0,0,1,1], frameon=False)

    plt.axis('off')
    plt.autoscale(tight=True)
    plt.ion()

    imageWindow = ax.imshow(np.zeros((1,1), dtype='uint8'), 
        interpolation='none')

    figure.canvas.draw()
    plt.show(block=False)

    return figure, imageWindow

def DisplayFrames(c, dispQueue):
    figure, imageWindow = draw_figure(c+1)
    while(True):
        if dispQueue:
            # dispQueue.popleft()
            imageWindow.set_data(dispQueue.popleft())
            figure.canvas.draw()
            figure.canvas.flush_events()
        else:
            time.sleep(0.01)
    plt.close(figure)