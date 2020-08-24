# campy
- Python package for streaming video from multiple cameras to disk. 
- Features real-time hardware-accelerated video compression and debayering using FFmpeg.

## Hardware/software
- Nvidia GPU(s) with NVENC (see https://developer.nvidia.com/video-encode-decode-gpu-support-matrix)
- Basler machine vision camera(s)
- Windows or Linux PC with dedicated channels for each camera interface (e.g. USB 3.0 or GigE ports with their own host controller)

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
pip install .
```
- Or manually install dependencies:
```
conda install numpy imageio imageio-ffmpeg scikit-image pyyaml
```

## Usage
- Use Basler Pylon Viewer to save your '.pfs' camera settings file. Examples are included in campy/cameras/basler/settings.
- Edit the config.yaml file to fit your system and recording configuration.
- To start your recording:
```
campy-acquire ./configs/config.yaml
```
- Press Ctrl^C to end recording before allotted recording time.
- Two files, "frametimes.npy" and "metadata.csv", will be saved along with the video file in each camera folder containing timestamps, frame numbers, and other recording metadata.

## Authors
Written by Kyle Severson and Diego Aldarondo (2019-2020).

## Credits
Special thanks to Tim Dunn, David Hildebrand, Paul Thompson, Zack Weaver, and Jim Roach for helpful comments.

## License
MIT License
