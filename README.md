# campy
- Python package for streaming video from multiple cameras to disk. 
- Features real-time hardware-accelerated video compression and debayering using FFmpeg.

## Hardware/software
- (Optional) AMD or Nvidia GPU for hardware encoding (see https://developer.nvidia.com/video-encode-decode-gpu-support-matrix)
- Basler and/or FLIR machine vision camera(s)
- Windows or Linux PC
- Arduino/Teensy microcontroller for syncing cameras

## Installation
1. Update graphics drivers
2. Create and activate a new Python 3.7 Anaconda environment:
```
conda create -n campy python=3.7 imageio-ffmpeg matplotlib -c conda-forge
conda activate campy
```
3. Install camera software
- If using Basler cameras, install Pylon software:
  - Install Basler Pylon with Developer options
  - Install pypylon:
  ```
  pip install pypylon
  ```
  - Alternatively, manually install pypylon (Basler's python wrappers for their pylon camera software suite):
  Download binary wheel from the [releases](https://github.com/Basler/pypylon/releases) page.
  ```
  pip3 install <wheel>
  ```

- If using FLIR cameras:
  - Download and install Spinnaker SDK and SpinView software from FLIR's website: 
    https://www.flir.com/support-center/iis/machine-vision/downloads/spinnaker-sdk-and-firmware-download/
  - Manually install binary wheel for PySpin (included in the Spinnaker download)
    E.g. for Python 3.7 on Windows amd64 system, install "spinnaker_python-2.3.0.77-cp37-cp37m-win_amd64.whl"
  ```
  pip3 install <wheel>
  ```
4. Clone or download campy to local folder:
```
git clone https://github.com/ksseverson57/campy.git
```
5. Update setuptools:
```
pip install -U setuptools
```
6. Finally, install campy and its dependencies (see setup.py) by navigating to campy folder:
```
pip install -e .
```

## Usage
- For Basler cameras, use the Pylon Viewer to save your '.pfs' camera settings file. Examples are included in campy/cameras/basler/settings.
- Edit the config.yaml file to fit your system and recording configuration.
- For help setting config parameters:
```
campy-acquire --help
```
- If using Python serial triggering, upload Arduino .ino file (in campy/triggers folder) to open serial COM.
- To start your recording:
```
campy-acquire ./configs/config.yaml
```
- If using external camera triggers, campy will wait until triggers start.
- Press Ctrl^C to end recording before allotted recording time.
- Three files, "frametimes.mat", "frametimes.npy", and "metadata.csv", will be saved along with the video file in each camera folder containing timestamps, frame numbers, and other recording metadata.

## Authors
Written by Kyle Severson with contributions from Diego Aldarondo and Iris Odstrcil (2019-2021).

## Credits
Special thanks to Tim Dunn, David Hildebrand, Vincent Prevosto, Manuel Levy, and Paul Thompson for helpful comments.

## License
MIT License
