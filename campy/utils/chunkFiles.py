import os
import imageio
import math
from subprocess import Popen
import sys
import time
import multiprocessing as mp

numCams = int(sys.argv[1])
chunkLengthInFrames = int(sys.argv[2])
fname = str(sys.argv[3])

basedir = os.getcwd()

# Get metadata from video (assuming all cameras are the same)
vid1 = os.path.join(basedir,'Camera1',fname)
vid = imageio.get_reader(vid1)
fps = vid.get_meta_data()['fps']
durationInSec = vid.get_meta_data()['duration']
durationInFrames = int(fps*durationInSec)
chunkLengthInSec = chunkLengthInFrames/fps
numChunks = math.ceil(durationInFrames/chunkLengthInFrames)

def chunkFiles(camNum):
    startFrame = 0
    endFrame = startFrame + chunkLengthInFrames - 1
    startTimeInSec = 0
    timeInSec = 0
    hrsStart = 0; minStart = 0; secStart = 0; msStart = 0

    viddir = os.path.join(basedir,'Camera' + str(camNum+1))
    fname_in = os.path.join(viddir,fname)
    for t in range(0,numChunks):

        outdir = os.path.join(viddir,'workspace')
        if not os.path.isdir(outdir):
            os.mkdir(outdir)
        fname_out = os.path.join(outdir,str(startFrame) + '_' + str(endFrame) + '.mp4')
        
        # No need to pad zeros
        startTime = str(hrsStart) + ':' + str(minStart) + ':' + str(secStart) + '.' + str(msStart)

        timeEnd = startTimeInSec + chunkLengthInSec
        hr = math.floor(timeEnd/3600)
        timeEnd = timeEnd - hr*3600
        mn = math.floor(timeEnd/60)
        timeEnd = timeEnd - mn*60
        sc = math.floor(timeEnd)
        timeEnd = timeEnd - sc
        ms = math.floor(timeEnd*1000)

        endTime = str(hr) + ':' + str(mn) + ':' + str(sc) + '.' + str(ms)

        cmd = ('ffmpeg -y -i ' + fname_in + ' -ss ' + startTime + ' -to ' + endTime + 
        ' -c:v copy -c:a copy ' + fname_out + ' -async 1 '
        ' -hide_banner -loglevel warning')

        if os.path.isfile(fname_out):
            print('Video ' + str(camNum+1) + ' chunk ' + str(t) + ' already exists...')
        else:
            p = Popen(cmd.split())
            print('Copying video ' + str(camNum+1) + ' chunk ' + str(t) + '...')
            time.sleep(5)

        startFrame = startFrame + chunkLengthInFrames
        endFrame = startFrame + chunkLengthInFrames - 1
        if endFrame > durationInFrames:
            endFrame = durationInFrames
        startTimeInSec = startTimeInSec + chunkLengthInSec
        hrsStart = hr
        minStart = mn
        secStart = sc
        msStart = ms

if __name__ == '__main__':            
    
    ts = time.time()
    print('Chunking videos...')
    pp = mp.Pool(numCams)
    pp.map(chunkFiles,range(0,numCams))