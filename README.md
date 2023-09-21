# This is an experimental branch currently under development
# Preparing new release (2.1.0) September 2023
- Added AV1 encoding support for better streaming quality per bit rate (see examples)
  Note: AV1 decoding may be slower than H264/265
- Added constant bitrate (cbr) mode
  With cbr, video files can be compressed consistently with minimal loss in visual quality
  However, constant quality (constqp) mode can compress with fewer artifacts in frames with rapid motion
- Integrated Basler pypylon zero-copy to reduce overhead
- Re-worked closeout sequence to improve synchronicity when recording is interrupted by user (Ctrl+C)
- Unified display window across camera APIs using opencv
- Added seamless chunking to split video into multiple files (see help for "chunkLengthInFrames")
- Replaced config parameter "chunkLengthInFrames" with "displayFrameCounter" for reporting FPS and recording progress
- Added support for non-integer frame rates
  Trigger module now passes inter-frame interval in microseconds rather than frame rate to microcontroller
  ** Re-upload trigger.ino if updating to campy 2.1 if using campy's included trigger module
- Minor bug fixes

# campy
- Python package for streaming video from multiple cameras 
- Features real-time hardware-accelerated video compression and debayering using FFmpeg

## Hardware/software
- Basler and/or FLIR machine vision camera(s)
- Windows 10/11 or Linux PC (Mac support not tested)
- (Optional) AMD or Nvidia GPU for hardware encoding (see https://developer.nvidia.com/video-encode-decode-gpu-support-matrix)
- (Optional) Arduino/Teensy microcontroller for syncing cameras and other recordings

## Installation
1. Update graphics drivers
2. Create and activate a new Python Anaconda environment:
```
conda create -n campy python=3.8 imageio-ffmpeg -c conda-forge
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
    https://www.flir.com/products/spinnaker-sdk
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

6. (Optional) Install your ffmpeg build of choice (e.g., 6.0.0 includes AV1 encoding support; however 4.2.2 supports h264/h265 best)
```
conda install ffmpeg==6.0.0 -c conda-forge
```
- Include in config.yaml:
```
ffmpegPath: "/path/to/ffmpeg.exe"
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
- Three files, "frametimes.mat", "frametimes.npy", "frametimes.csv", "writer_frametimes.csv", and "metadata.csv", will be saved along with the video file in each camera folder containing timestamps, frame numbers, and other recording metadata.

### Helpful Tips
- Check that your cameras and features can be loaded in the camera vendor's GUI (e.g. Pylon Viewer for Basler).
- Try replugging USB cables if cameras cannot be found or saving new camera features if errors arise during loading of camera settings

- If your compression streams are limited to 5 random cameras, it could be due to hard limit of 5 simultaneous encoding streams per system when using NVIDIA Geforce cards
- Tesla/Quadro cards are typically unrestricted
- NVIDIA driver patch can circumvent this restriction

- To debug broken ffmpeg pipe error, up the ffmpeg log level in config.yaml:
```
ffmpegLogLevel: "warning"
```
- Use the command "ffmpeg" to check enabled packages. Hardware encoder support must be enabled in your ffmpeg binary.
- Windows ffmpeg binary installed by Anaconda should have hardware encoder support enabled by default.
- On Linux, you may need to compile your own ffmpeg binary to enable certain codecs, filters, or plugins:
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
Written by Kyle Severson with contributions from Diego Aldarondo and Iris Odstrcil.

## Credits
Special thanks to Paul Thompson, Tim Dunn, Talmo Pereira, David Hildebrand, Vincent Prevosto, and Manuel Levy for helpful comments.

## License
MIT License
(2019-2023)
