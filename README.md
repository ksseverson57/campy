# CamPy
- Python package for streaming video from multiple cameras to disk. 
- Features real-time hardware-accelerated video compression and debayering using FFmpeg.

## Hardware
- Nvidia GPU(s) with NVENC (Maxwell 2nd Gen or newer)
- Basler machine vision camera(s)
- PC with dedicated ports (e.g. USB 3.0 or GigE) for each camera

## Installation
- Install Basler Pylon 6 with Developer options
- Update Nvidia GeForce Experience to latest drivers
- Install pypylon (Basler's python wrappers for their pylon camera software suite):
```
git clone https://github.com/basler/pypylon.git
cd pypylon
pip install .
```
- Install dependencies by navigating to campy folder:
```
python setup.py install
```

## Usage
- Supported on Windows and Linux machines
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
