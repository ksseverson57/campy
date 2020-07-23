
import pypylon.pylon as pylon
import pypylon.genicam as geni

import os
import time

import numpy as np
from collections import deque

def Open(c, camSettings, bufferSize=500, validation=True):

    # Open and load features for all cameras
    tlFactory = pylon.TlFactory.GetInstance()
    devices = tlFactory.EnumerateDevices()
    camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateDevice(devices[c]))
    serial = devices[c].GetSerialNumber()
    camera.Close()
    camera.StopGrabbing()
    camera.Open()
    pylon.FeaturePersistence.Load(camSettings, camera.GetNodeMap(), validation)
    print("Started camera", c, "serial#", serial)

    # Start grabbing frames (OneByOne = first in, first out)
    camera.MaxNumBuffer = bufferSize
    camera.StartGrabbing(pylon.GrabStrategy_OneByOne)

    print("Camera", c, "ready to trigger.")

    return camera

def GrabFrames(c, camera, displayQueue, writeQueue, 
                frameRate=100, recTimeInSec=10, 
                displayFrameRate=10, displayDownSample=2):
    
    chunkSizeInSec = 30
    cnt = 0
    displayCount = 0
    timeout = 0

    # Initialize metadata to be saved in numpy file
    meta = {}
    meta['TimeStamp'] = []
    meta['FrameNumber'] = []

    frameRatio = int(round(frameRate/int(displayFrameRate)))
    ds = displayDownSample

    numImagesToGrab = recTimeInSec*frameRate
    chunkSizeInFrames = chunkSizeInSec*frameRate 

    while(camera.IsGrabbing()):
        try:
            if cnt >= numImagesToGrab:
                camera.StopGrabbing()
                break

            try:
                # Grab image from camera buffer if available
                grabResult = camera.RetrieveResult(timeout, pylon.TimeoutHandling_ThrowException)

                # Append numpy array to writeQueue for writer to append to file
                writeQueue.append(grabResult.Array)

                if cnt == 0:
                    timeFirstGrab = grabResult.TimeStamp
                grabtime = (grabResult.TimeStamp - timeFirstGrab)/1e9
                meta['TimeStamp'].append(grabtime)

                cnt += 1
                meta['FrameNumber'].append(cnt) # first frame = 1

                if cnt % frameRatio == 0:
                    displayQueue.append(grabResult.Array[::ds,::ds])

                if cnt % chunkSizeInFrames == 0:
                    fps_count = int(round(cnt/grabtime))
                    print('Camera %i collected %i frames at %i fps.' % (c,cnt,fps_count))

                grabResult.Release()
   
            # Else wait for next frame available
            except geni.GenericException:
                time.sleep(0.0001)

        except KeyboardInterrupt:
            camera.StopGrabbing()
            break

    return meta


def Close(c, camera):

	print('Closing camera {}... Please wait.'.format(str(c+1)))

	# Close Basler camera after acquisition stops
	while(True):
		try:
			try:
				camera.Close()
				break
			except:
				time.sleep(0.1)
		except KeyboardInterrupt:
			break

def SaveMetadata(c, meta, videoFolder):

	cnt = meta['FrameNumber'][-1]
	fps_count = str(int(round(cnt/meta['TimeStamp'][-1])))
	print('Camera {} saved {} frames at {} fps.'.format(c+1, cnt, fps_count))
	x = np.array([meta['FrameNumber'], meta['TimeStamp']])
	fname = os.path.join(videoFolder, 'Camera' + str(c+1), 'metadata.npy')

	np.save(fname,x)
