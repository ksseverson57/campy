# campy
- Python package for streaming video from multiple cameras to disk. 
- Features real-time hardware-accelerated video compression and debayering using FFmpeg.

## Hardware/software
- AMD or Nvidia GPU for hardware encoding (see https://developer.nvidia.com/video-encode-decode-gpu-support-matrix)
- Flir and/or Basler machine vision camera(s)
- Windows or Linux PC

## Installation
- Update graphics to latest drivers
- Create and activate a new Python 3.7 Anaconda environment:
```
conda create -n campy python=3.7 imageio ffmpeg matplotlib
conda activate campy
```
- Optionally, manually install dependencies:
```
conda install numpy imageio imageio-ffmpeg scikit-image pyyaml
```
- To install Basler camera software:
- Install Basler Pylon 6 with Developer options
- Install pypylon (Basler's python wrappers for their pylon camera software suite):
```
Download a binary wheel from the [releases](https://github.com/Basler/pypylon/releases) page.
E.g. for Python 3.7 on Windows amd64 system, download "pypylon-1.6.0rc1-cp37-cp37m-win_amd64.whl"
E.g. for Python 3.7 on Linux x86 system, download "pypylon-1.6.0rc1-cp37-cp37m-linux_x86_64.whl"
Install the wheel using ```pip3 install <wheel>```
```
- To install FLIR camera software:
- Download Spinnaker SDK and SpinView software from FLIR's website: 
- https://www.flir.com/support-center/iis/machine-vision/downloads/spinnaker-sdk-and-firmware-download/
- Install the appropriate binary wheel for PySpin (included in the Spinnaker download)
```
E.g. for Python 3.7 on Windows amd64 system, install "spinnaker_python-2.3.0.77-cp37-cp37m-win_amd64.whl"
Install the wheel using ```pip3 install <wheel>```
```
- Clone or download campy to local folder
- Install campy and other dependencies by navigating to campy folder:
```
python setup.py install
pip install .
```

## Usage
- For Basler camera, use the Pylon Viewer to save your '.pfs' camera settings file. Examples are included in campy/cameras/basler/settings.
- Edit the config.yaml file to fit your system and recording configuration.
- For help with setting config parameters:
```
campy-acquire --help
```
- To start your recording:
```
campy-acquire ./configs/config.yaml
```
- Press Ctrl^C to end recording before allotted recording time.
- Two files, "frametimes.npy" and "metadata.csv", will be saved along with the video file in each camera folder containing timestamps, frame numbers, and other recording metadata.

## Authors
Written by Kyle Severson, Diego Aldarondo, and Iris Odstrcil (2019-2021).

## Credits
Special thanks to Tim Dunn, David Hildebrand, and Paul Thompson for helpful comments.

## License
MIT License
