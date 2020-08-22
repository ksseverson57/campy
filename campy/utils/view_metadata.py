
import os
import sys
from pprint import pprint
import numpy as np
import scipy.io

# Usage: python "C:\\Code\\campy\\utils\\view_metadata.py" folder_name file_name numCams
# python "C:\\Code\\campy\\utils\\view_metadata.py" "D:\\20200401\\test\\videos" "metadata.npy" 6

folder_name = str(sys.argv[1])
file_name = str(sys.argv[2])
numCams =  int(sys.argv[3])

num_IFI = 30
m = 0
y = list()
for c in range(0,numCams):
    full_folder_name = os.path.join(folder_name, 'Camera' + str(c+1))
    full_file_name = os.path.join(full_folder_name, file_name)

    x = np.load(full_file_name)
    y.append(x)

    np.set_printoptions(precision=8)
    np.set_printoptions(suppress=True)
    np.set_printoptions(threshold=np.inf)
    #print(x)

    xdiff = np.diff(x[1,:])
    xdiff_sorted = np.sort(xdiff)
    print('Printing {} largest inter-frame intervals:'.format(num_IFI))
    print(np.flip(xdiff_sorted)[0:num_IFI-1])

    mindiff = min(xdiff)
    maxdiff = max(xdiff)
    totalFrames = int(np.round(x[0,-1]))
    totalTime = x[1,-1]
    frameRate = 1/(totalTime/totalFrames)

    print('First frame time: {:.8f} sec.'.format(x[1,1]))
    print('Last frame time :{:.8f} sec.'.format(x[1,-1]))
    print('Min inter-frame interval: {:.8f} sec.'.format(mindiff))
    print('Max inter-frame interval: {:.8f} sec.'.format(maxdiff))
    print('Total frames: {} frames.'.format(totalFrames))
    print('Total time: {:.2f} sec.'.format(totalTime))
    print('Avg frame rate: {:.2f} fps.'.format(frameRate))

    output_file_name = os.path.join(full_folder_name, 'metadata.mat')
    scipy.io.savemat(output_file_name, dict(x=x))

