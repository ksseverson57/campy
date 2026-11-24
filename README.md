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
2. Create and activate a new Python 3.7+ Anaconda environment:
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

### Console output
By default, each camera prints every setup step as it happens, and with several cameras those lines are mixed together. For one line per camera instead, include this in config.yaml:
```
consoleSummary: True
```
Each camera then prints one line once it is ready to trigger, with its make, model, serial number, frame size and rate, the settings campy gave it and the video it records into, and one line at the end with the frames it saved and what its video holds:
```
Camera1 ready to trigger: flir Blackfly S BFS-U3-13Y3M serial 23501329, 1280x1024 at 80 fps, trigger Line3, exposure 750 us, gain 3 dB, gamma off, 100 buffers (Oldest First), h264 on CPU -> ./test/Camera1/0.mp4
...
Camera1 saved 24000 frames at 80 fps and its metadata: ./test/Camera1/0.mp4 holds all of them.
```
Problems are still printed straight away (campy's own messages name their camera; errors from Python's logging keep their usual `ERROR:root:` form). A camera that does not get ready prints every step it took. With `cameraDebug: True`, every step is printed as before.

While recording, each camera prints a progress line every `chunkLengthInSec`. For one status line at the bottom of the console instead, rewritten in place about once a second, include this in config.yaml:
```
statusLine: "auto"
```
```
Recording 3:00 · Camera0 10,800 · Camera1 10,800 · Camera2 10,800 frames · 60.0 fps
```
It shows the time since the first frame, each camera's frame count and the frame rate over the last 5 s (each camera's own rate when they differ). Every other message still prints as its own line above it. `"auto"` shows it only when the output is a console: output redirected to a file or a pipe keeps the progress lines. `"always"` shows it anyway (the log then holds the console codes), and `"never"` (the default) keeps the progress lines.

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
