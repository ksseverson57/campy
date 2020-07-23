"""

"""
from imageio import get_writer
import os
import time

def OpenWriter(
		c, # camera index
		videoFolder, # video folder
		frameRate,
		gpu=0, # idx of gpu
		quality=19, # int 0-55, 0 is lossless, 19-21 is "visually lossless"
		# vf='scale=iw:ih', # debayer 'scale=src_format=bayer_bggr8'
		fname='0',
		ext='.mp4',
		loglevel='quiet', # 'warning', 'quiet', 'info'
		):

    folder_name = os.path.join(videoFolder, 'Camera' + str(c+1))
    file_name = os.path.join(folder_name, fname + ext)
    
    while(True):
        try:
            try:
                writer = get_writer(
                    file_name, 
                    fps = frameRate, 
                    codec = 'h264_nvenc',  # GPU-accel'd encoding 'h264_nvenc' 'hevc_nvenc'
                    mode = 'I',
                    quality = None,  # disables variable compression
                    pixelformat = 'rgb0',  # keep it as RGB colours
                    ffmpeg_log_level = loglevel,
                    ffmpeg_params = [
                        '-preset', 'fast',
                        # '-zerolatency', '1',
                        '-qp', str(quality),
                        # '-vf', vf,
                        '-pix_fmt', 'rgb0',
                        '-bf:v', '0',
                        '-gpu', str(gpu)],)
                print('Opened:', file_name, 'using GPU', gpu)
                break

            except FileNotFoundError:
                os.makedirs(folder_name)
                print('Made directory {}.'.format(folder_name))
            except:
                time.sleep(0.01)
        except KeyboardInterrupt:
            break

    return writer

def WriteFrames(c, writer, writeQueue, frameTimeInSec, frameRate):
    countOfImagesToGrab = frameTimeInSec*frameRate
    cnt = 0
    while(True):
        try:
            if writeQueue:
                writer.append_data(writeQueue.popleft())
                cnt+=1
            else:
                time.sleep(0.0001)

            if cnt == countOfImagesToGrab:
                time.sleep(1)
                writer.close()
                break

        except KeyboardInterrupt:
            try:
                print('Closing video writer for camera {}. Please wait...')
                time.sleep(5)
                writer.close()
                break
            except KeyboardInterrupt:
                writer.close()
                break