# campy
- Python package for streaming video from multiple cameras to disk. 
- Features real-time hardware-accelerated video compression and debayering using FFmpeg.

## Hardware
- Nvidia GPU(s) with NVENC (Maxwell 2nd Gen or newer)
- Basler machine vision camera(s)
- PC with dedicated channels for each camera interface (e.g. USB 3.0 or GigE ports with their own host controller)

## Installation
- Install Basler Pylon 6 with Developer options
- Update Nvidia GeForce Experience to latest drivers
- Create and activate a new Python 3.7 Anaconda environment:
```
conda create -n campy python=3.7 imageio ffmpeg matplotlib
conda activate campy
```
- Install pypylon (Basler's python wrappers for their pylon camera software suite):
```
Download a binary wheel from the [releases](https://github.com/Basler/pypylon/releases) page.
E.g. for Python 3.7 on Windows amd64 system, download "pypylon-1.6.0rc1-cp37-cp37m-win_amd64.whl"
E.g. for Python 3.7 on Linux x86 system, download "pypylon-1.6.0rc1-cp37-cp37m-linux_x86_64.whl"
Install the wheel using ```pip3 install <your downloaded wheel>.whl```
```
- Install other dependencies by navigating to campy folder:
```
python setup.py install
```
- Or manually install dependencies:
```
conda install numpy imageio imageio-ffmpeg scikit-image
```

## Usage
- Supported on Windows and Linux machines
- Use Basler Pylon Viewer to save your '.pfs' camera settings file
- To start your recording:
```
python campy.py videoFolder pylonFeatureFile numCams frameRate recordingTimeInSec
```
- Press Ctrl^C to end recording before allotted recording time
- A "metadata.npy" file will be saved along with the video file in each camera folder containing timestamps, frame numbers, and other recording data.

## Authors
Written by Kyle Severson (2019-2020)

## Credits
Special thanks to Tim Dunn, David Hildebrand, and Diego Aldarondo for helpful comments.

## License
