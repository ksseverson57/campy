"""
Displays captured camera frames in performant openCV window
"""
import time
import cv2

def DisplayFrames(cam_params, dispQueue):
	
	window_name = cam_params['cameraName']
	cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)

	window_open = True
	displaying = True

	while(displaying):
		try:
			if dispQueue:
				img = dispQueue.popleft()

				# If stop message received, exit the loop
				if isinstance(img, str):
					displaying = False
					break

				# Otherwise display queued image
				else:
					if window_open:
						# opencv expects mono or BGR
						cv2.imshow(window_name, img)

						# If user presses "q", close window
						keypressed = cv2.waitKey(30)
						if keypressed == ord('q'):
							window_open = False
							break

						# If user manually closes window, stay closed
						if cv2.getWindowProperty(
							window_name, cv2.WND_PROP_VISIBLE
							) < 1:        
							window_open = False
							break

			else:
				time.sleep(0.01)

		except KeyboardInterrupt:
			break

		except:
			time.sleep(0.01)

	# cv2.waitKey(0)
	cv2.destroyAllWindows()
	time.sleep(0.01)