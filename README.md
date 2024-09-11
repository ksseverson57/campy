# campy
- Python package for acquiring and compressing video from multiple cameras

## Hardware/Software Recommendations
- Basler and/or FLIR machine vision camera(s)
- Windows, IOS, or Linux system
- (Optional) Server/workstation class CPUs with >=4 memory channels (e.g., AMD Threadripper 3995WX, Intel i9-10900X) can increase bandwidth over consumer CPUs with 2 memory channels (more cameras, higher resolution/frame rate)
- (Optional) USB expansion card with 1 host controller per camera (e.g., Basler USB 3.0, 4X PCIe, 4X HC, 4 Ports PN# 2000036233)
- (Optional) Hardware encoder using AMD, Intel, or Nvidia GPU (see https://developer.nvidia.com/video-encode-decode-gpu-support-matrix)
- (Optional) Arduino/Teensy/Pi microcontroller for syncing cameras and other devices

## Installation
1. Update graphics drivers
2. Create and activate a new Python 3.7 Anaconda environment:
```
conda create -n campy python=3.7 imageio-ffmpeg matplotlib ffmpeg==4.2.2 -c conda-forge
conda activate campy
pip install -U setuptools
```
3. Install camera software
- If using Basler cameras, install Pylon software:
  - Install Basler Pylon with Developer options
  - Install pypylon:
  Windows:
  ```
  pip install pypylon
  ```
  Linux:
  ```
  conda install swig
  git clone https://github.com/basler/pypylon.git
  python ./pypylon/setup.py install
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
5. Finally, install campy and its dependencies (see setup.py) by navigating to campy folder:
```
pip install -e .
```

## Usage

### Configuration
- For Basler cameras, use the Pylon Viewer to configure and save your '.pfs' camera settings file. Examples are included in campy/configs.
- Edit the config.yaml file to fit your system and recording configuration.
- Several example config files are located in campy/configs.
- For help setting config parameters:
```
campy-acquire --help
```

### Camera Triggering
Campy's trigger module supports Arduino and Teensy microcontrollers:
1. Download Arduino IDE (https://www.arduino.cc/en/software). If using Teensy, install Teensyduino (https://www.pjrc.com/teensy/teensyduino.html).
2. Connect your microcontroller and note its port number (e.g. "COM3" on Windows or "/dev/ttyACM0" on Linux).
3. In your config.yaml, configure:
```
startArduino: True 
digitalPins: [<pin IDs>] # e.g. [0,1,2]
serialPort: "<port>" # e.g. "COM3" or "/dev/ttyACM0"
```
4. Open and upload "trigger.ino" file (in campy/trigger folder) to your board. Make sure serial monitor is closed while using pyserial connection.
5. Campy will synchronously trigger the cameras once acquisition has initialized.

### Start Recording:
```
campy-acquire ./configs/campy_config.yaml
```

### Stop Recording:
- Campy can be configured to stop automatically after set recording time (e.g. 1 hour):
```
recTimeInSeconds: 3600
```
- To manually end, press Ctrl^C. Wait until campy exits!
- Three files, "frametimes.mat", "frametimes.npy", and "metadata.csv", will be saved along with the video file in each camera folder containing timestamps, frame numbers, and other recording metadata.

### Helpful tips
- To debug broken ffmpeg pipe error, include this in config.yaml:
```
ffmpegLogLevel: "warning"
```
- Use the command "ffmpeg" to check enabled packages. Hardware encoder support must be enabled in your ffmpeg binary.
- Windows ffmpeg binary installed by Anaconda should have hardware encoder support enabled by default.
- On Linux, you may need to compile your own ffmpeg binary to enable encoders:
- Nvidia:
```
git clone https://git.videolan.org/git/ffmpeg/nv-codec-headers.git
cd nv-codec-headers && sudo make install && cd ..
```
- Intel:
```
sudo apt-get install libva-dev libmfx-dev libx264-dev libx265-dev libnuma-dev
```
- AMD:
```
git clone https://github.com/GPUOpen-LibrariesAndSDKs/AMF.git
sudo cp -r ./AMF/amf/public/include/core /usr/include/AMF
sudo cp -r ./AMF/amf/public/include/components /usr/include/AMF
```
- Compile ffmpeg:
```
git clone https://git.ffmpeg.org/ffmpeg.git
cd ffmpeg
sudo ./configure \
--enable-cuda --enable-cuvid --enable-nvdec --enable-nvenc --enable-nonfree \
--extra-cflags=-I/usr/local/cuda/include --extra-ldflags=-L/usr/local/cuda/lib64 \
--enable-gpl --enable-libx264 --enable-libx265 --enable-libmfx \
--enable-amf
sudo make -j -s
sudo cp -r ./ffmpeg /usr/bin
```
- Include in config.yaml:
```
ffmpegPath: "/usr/bin/ffmpeg"
```

## Authors
Written by Kyle Severson with contributions from Diego Aldarondo and Iris Odstrcil (2019-2021).

## Credits
Special thanks to Tim Dunn, David Hildebrand, Vincent Prevosto, Manuel Levy, and Paul Thompson for helpful comments.

## License
MIT License
