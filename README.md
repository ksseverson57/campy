# campy
- Python package for acquiring synchronized video from multiple cameras with real-time compression

## Hardware/Software Recommendations
- Basler and/or FLIR machine vision camera(s)
- Windows, IOS, or Linux system
- (Recommended) Server/workstation class CPUs with >=4 memory channels (e.g., AMD Threadripper 3955WX-9955WX, Intel i9-10900X, Xeon) can increase bandwidth over consumer CPUs with 2 memory channels (more cameras, higher resolution/frame rate).
- (Recommended) High core count CPUs are not necessary, but generally >1 core per camera is recommended, as campy leverages one process per camera using multiprocessing for parallelism.
- (Optional) USB expansion card with 1 host controller per camera (e.g., Basler USB 3.0, 4X PCIe, 4X HC, 4 Ports PN# 2000036233).
- (Optional) Hardware encoder using AMD, Intel, or Nvidia GPU (see https://developer.nvidia.com/video-encode-decode-gpu-support-matrix).
- (Optional) Arduino/Teensy/Pi microcontroller for syncing cameras and other devices.

## Installation
1. Update graphics drivers
2. Create and activate a new Anaconda environment with Python 3.12 and ffmpeg 8.1. Use the Python your camera software is built for: FLIR's PySpin (Spinnaker 4.4) is built for Python 3.12 on Windows, macOS and Ubuntu 24.04, and for Python 3.10 only on Ubuntu 22.04, so use `python=3.10` there. Older Pythons are not recommended: current imageio-ffmpeg needs Python 3.10 or newer.
```
conda create -n campy python=3.12 imageio-ffmpeg matplotlib ffmpeg=8.1 -c conda-forge
conda activate campy
pip install -U setuptools
```
To encode on an NVIDIA GPU, check this ffmpeg first: see [NVIDIA GPU encoding (NVENC)](#nvidia-gpu-encoding-nvenc) below.

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
    It must match your Python by its cpXY tag, and the Spinnaker SDK you installed by its version. E.g. for Spinnaker 4.4.0.246 and Python 3.12 on Windows, install "spinnaker_python-4.4.0.246-cp312-cp312-win_amd64.whl"
  ```
  pip3 install <wheel>
  ```
4. Create a folder to clone campy:
```
cd ~\Documents\
mkdir campy
cd campy
```
5. Clone or download campy to local folder:
```
git clone https://github.com/ksseverson57/campy.git
```
6. Navigate to the cloned campy folder
```
cd campy
```
7. Finally, install campy and its dependencies (see setup.py):
```
pip install -e .
```

### NVIDIA GPU encoding (NVENC)
`gpuMake: "nvidia"` needs an ffmpeg that is 4.4 or newer and is built for an NVENC version the NVIDIA driver supports.
- ffmpeg 4.3 and older ask the driver for NVENC presets with a call that NVIDIA drivers from 591.44 (December 2025) reject for H.264 and HEVC. Every camera's writer then stops with a broken pipe, and ffmpeg's error is `Cannot get the preset configuration: unsupported param (12)`. These instructions used to pin `ffmpeg==4.2.2`, so environments made with them have this problem: make a new environment as above, or set `ffmpegPath` to a newer ffmpeg (below).
- An ffmpeg built for a newer NVENC version than the driver supports fails the other way and says what it needs, e.g. `Driver does not support the required nvenc API version. Required: 13.1 Found: 13.0`. Update the driver, or use an ffmpeg built for the NVENC version the driver has.

conda-forge's ffmpeg comes in builds for several NVENC versions, and conda picks one the driver supports when it creates the environment, by the CUDA version `nvidia-smi` shows: 12.8 or newer (driver 570 or newer) gets NVENC 13.0, and 12.2 to 12.7 an older NVENC version. With a driver older than 535 it gets an ffmpeg without NVENC: update the driver, or set `ffmpegPath`.

To use another ffmpeg, put its path in the config; campy passes it to imageio-ffmpeg:
```
ffmpegPath: 'C:\ffmpeg\bin\ffmpeg.exe'
```
BtbN's builds (https://github.com/BtbN/FFmpeg-Builds/releases) take their NVENC version from the ffmpeg version: 8.0 and 8.1 are built for NVENC 13.0 (driver 570 or newer), 9.x and master for NVENC 13.1 (driver 610 or newer).

To check a computer before recording, encode two seconds of test frames, without cameras, with the ffmpeg campy will use (`python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"` prints its path):
```
ffmpeg -hide_banner -f lavfi -i testsrc2=size=1280x1024:rate=60 -t 2 -pix_fmt rgb0 -c:v hevc_nvenc -preset fast -qp 24 -bf:v 0 -gpu 0 -y nvenc_test.mp4
```
It passes if it writes nvenc_test.mp4 and prints no errors. These are campy's settings for `codec: "h265"`, `quality: 24` and `gpuID: 0`; `codec: "h264"` uses `h264_nvenc`.

For `preset`, `"fast"` (campy's default) works in every ffmpeg, and `p1` (fastest) to `p7` (best quality) from 4.4 on, where `"fast"` means `p1`, NVENC's fastest preset (4.2.2 used the older "high performance" preset). ffmpeg 9 removed the older names, such as `llhp` and `llhq`.

### AV1 on a GPU
`codec: "av1"` encodes AV1 on the GPU's encoder: `av1_nvenc` with `gpuMake: "nvidia"` (Ada generation, such as the RTX 40-series and RTX Ada cards, and newer), `av1_qsv` with `"intel"` (Arc GPUs, and the integrated GPUs of Core Ultra processors) and `av1_amf` with `"amd"` (RDNA 3, such as the Radeon RX 7000-series, and newer). Other GPUs have no AV1 encoder, and ffmpeg stops with an error. AV1 is for GPU encoding only: with `gpuID: -1` campy stops and says so.
- `quality` is then AV1's quantizer index, 0-255, not the 0-51 of H.264 and H.265, and is passed to every encoder as it is (Quick Sync H.264 and H.265 get `quality` + 1). 88 is a place to start: on an Intel Core Ultra's Quick Sync (1280x1024 mono, 60 fps) it gave files about half the size of H.265 at quality 24. Check the picture and file size on your own scene.
- `av1_qsv` needs an ffmpeg built with Intel's oneVPL (`libvpl`). conda-forge's ffmpeg 8.1.2 for Linux is; its Windows build has no `_qsv` encoders at all, so set `ffmpegPath` to one that does, such as BtbN's builds above (which have NVENC too). To compile ffmpeg for it, configure with `--enable-libvpl` (apt package `libvpl-dev`), not `--enable-libmfx`.
- `ffmpeg -hide_banner -encoders` lists the encoders an ffmpeg has: look for `av1_nvenc`, `av1_qsv` or `av1_amf`.
- Check that your analysis tools read AV1 before recording in it: OpenCV's wheels for Linux, for one, decode no AV1. ffmpeg-based readers such as PyAV and imageio-ffmpeg do.

## Usage

### Configuration
- For Basler cameras, use the Pylon Viewer to configure and save your '.pfs' camera settings file. Examples are included in campy/configs.
- Edit the config.yaml file to fit your system and recording configuration.
- Several example config files are located in campy/configs.
- For help setting config parameters:
```
campy-acquire --help
```
- H.265 on a Mac: MATLAB's VideoReader, QuickTime and Safari use Apple's decoder, which opens H.265 in an .mp4 or .mov only when the file tags it `hvc1` (ffmpeg's own tag is `hev1`). To record H.265 they can open, include in config.yaml:
```
codec: "h265"
macCompatibleH265: True
```
  This tags the video `hvc1` for every encoder, and with the CPU (`gpuID: -1`) also asks libx265 for closed GOPs (`-x265-params open-gop=0`): Apple's decoder fails on libx265's default open GOPs even when the file is tagged `hvc1`. The default, `False`, records as before. An existing .mp4 can be retagged without re-encoding: `ffmpeg -i 0.mp4 -c copy -tag:v hvc1 0-hvc1.mp4` (a libx265 video keeps its open GOPs).

### Camera Triggering
Campy's trigger module supports Python integration with Arduino and Teensy microcontrollers:
1. Download Arduino IDE (https://www.arduino.cc/en/software). If using Teensy, install Teensyduino (https://www.pjrc.com/teensy/teensyduino.html).
3. Connect your microcontroller via USB and note the serial port number (e.g., "COM3" in Windows Device Manager or "/dev/ttyACM0" on Linux).
4. Connect the camera GPIO wires to the microcontroller digital outputs. Note the digital pin numbers (e.g., DO1, DO2, etc.) for each camera. For best results, securely solder the pins. Be careful to use the correct voltage recommended by the camera manufacturer.
5. In your campy config.yaml, configure:
```
startArduino: True
cameraTrigger: "Line0" # or "Line3", whichever color wire you used, but be consistent!
digitalPins: [<pin IDs>] # e.g., [0,1,2]
serialPort: "<port>" # e.g., "COM3" or "/dev/ttyACM0"
triggerController: "arduino"
```
4. Open and upload the "trigger.ino" file (in campy/trigger folder) to your board. Make sure the baudrate is set to 115200, and the serial monitor is closed while using pyserial connection.
5. Campy can now communicate with the microcontroller to synchronously trigger the cameras once acquisition has initialized.

Alternatively, to configure campy for external triggering:
Start campy before triggering. Campy will wait for external triggers to initialize. To stop the recording, either configure a set recording time in campy or stop triggers before manually exiting campy (see Stop Recording below). 
```
startArduino: False
cameraTrigger: "Line0" # or "Line3"
```

### Start Recording:
```
campy-acquire ./configs/campy_config.yaml
```

### Stop Recording:
- Campy can be configured to stop automatically after set recording time (e.g., 1 hour):
```
recTimeInSeconds: 3600
```
- To manually end, press Ctrl^C. Please wait until campy exits!
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
Written by Kyle Severson with contributions from Diego Aldarondo and Iris Odstrcil.

## Credits
Special thanks to Stefan Oline, Tim Dunn, David Hildebrand, Vincent Prevosto, Manuel Levy, and Paul Thompson for helpful comments.

## License
MIT License
