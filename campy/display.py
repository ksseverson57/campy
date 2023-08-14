"""

"""
import time
import cv2

def DisplayFrames(cam_params, dispQueue):
	displaying = True
	while(displaying):
		try:
			if dispQueue:
				img = dispQueue.popleft()
				if isinstance(img, str):
					displaying = False
				else:
					cv2.imshow("Camera" + str(cam_params['n_cam']+1), img) # cv2 expects mono or BGR
					keypressed = cv2.waitKey(30)
					if keypressed == ord('q'):
						break
			else:
				time.sleep(0.01)
		except KeyboardInterrupt:
			break

	cv2.destroyAllWindows()