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

### Display
By default each camera opens a preview window of its own. To see every camera side by side in one window instead:
```
displayMode: "one-window" # default: "per-camera"
displayFrameRate: 10 # frames per second shown for each camera
displayDownsample: 2 # each shown frame is 1/2 the width and height
```
- The window runs in a process of its own, at a lower priority than the cameras. A camera never waits for it: if the window falls behind, or you close it, the frames it has not taken yet are skipped, and the recording goes on. It closes when the recording ends.
- Each camera's badge shows its frame rate, or in red what is wrong: SLOW (below 95% of frameRate), DROPPED (frames missing from the camera's timestamps), ENCODER BEHIND (frames waiting to be written), or NO FRAMES (none for 3 s; that camera's last frame stays dimmed while the others go on).
- Double click a camera to see it alone, and again to see every camera. The mouse wheel zooms into a camera about the pointer; drag to move it; 0 shows the whole frame again. Keys 1-9 show one camera, the arrow keys the previous or next one, g or Esc every camera.

### Start Recording:
```
campy-acquire ./configs/campy_config.yaml
```

### A new session folder for each run (optional)
By default each camera records into `<videoFolder>/<cameraName>/`, and a second run with the same config replaces the first one's files. To keep every run, set:
```
sessionFolder: True # or, for one run: campy-acquire config.yaml --sessionFolder True
```
Each run then records into a new folder inside `videoFolder`, named by the date and time it started, which campy prints as it starts (`Recording into ...`). Two runs started in the same second get `..._14-05-11` and `..._14-05-11_2`, so no run records into another's folder:
```
test/
  2026-11-24_14-05-11/
    Camera0/
      0.mp4
      frametimes.npy, frametimes.mat, metadata.csv
    Camera1/ ...
```
This is the session folder layout that multi-camera tools such as [LUC3D](https://github.com/talmolab/luc3d) (Load Session Folder) and [sleap-anipose](https://github.com/talmolab/sleap-anipose) read: one folder per camera, named as the camera is named in the calibration. Put the calibration file (`calibration.toml`) in the run's folder, beside the camera folders. To load several runs at once in LUC3D, pick `videoFolder` itself.

A calibration recording, one whose `videoFilename` has "calibration" in it (`--videoFilename calibration.mp4`), puts each camera's video into `<cameraName>/calibration_images/`, where those tools look for a camera's calibration video and never mistake it for a session video. The camera's other files stay in `<cameraName>/`. Give calibration recordings a `videoFolder` of their own (`--videoFolder ./calibrations`), so that loading several runs at once doesn't take a calibration run for a session with no videos. Without `sessionFolder`, a calibration video is saved like any other.

Each camera's "metadata.csv" records the run's folder as `recordingFolder`. With `sessionFolder`, two cameras with the same name (`cameraNames`, compared ignoring case) would write into one folder, so campy stops before recording and says which.

### Calibrating the cameras (optional)
campy can help record a calibration video and then calibrate every camera from it with [calibrat3](https://github.com/talmolab/calibrat3), giving the `calibration.toml` that [LUC3D](https://github.com/talmolab/luc3d) and [sleap-anipose](https://github.com/talmolab/sleap-anipose) use for 3D.

**What to install** (only for this; recording without it needs none of them):
- `pip install opencv-python` (4.7 or newer), for the calibration view;
- a calibrat3 checkout: `git clone https://github.com/talmolab/calibrat3`;
- either [Node.js](https://nodejs.org) 20 or newer, which runs calibrat3's command line, or Google Chrome and `pip install playwright`, which runs calibrat3's page in Chrome without showing it (Playwright uses the installed Chrome; no browser download is needed).

**1. The board.** Print or buy a ChArUco board and tell campy which it is:
```
calibrationBoard: "CCT300200C" # a calib.io board, by SKU or id (calibio-300x200-coarse)
```
- calib.io's 13 stock ChArUco boards are known by their SKU (e.g. `CCT300200C`) or id (`calibio-300x200-coarse`); campy fills in their squares, sizes and dictionary.
- `calibrationBoard: "auto"` identifies a calib.io board from its markers while you record. calib.io sells most grids in two or three sizes, which a video can't tell apart: give the square size too (`calibrationSquareMm: 20`).
- Any other board: `calibrationBoard: {board_x: 8, board_y: 11, square_length: 24, marker_length: 18.75, marker_bits: 4, dict_size: 1000}` (squares across and down, the square and marker sides in mm, and the ArUco dictionary: here `DICT_4X4_1000`), as sleap-anipose's `board.toml`.

**2. The calibration view.** In the one window (`displayMode: "one-window"`), press `c`, or start with it on:
```
calibrationMode: True # also sets displayMode: "one-window"
```
Each camera's tile then shows the board's corners as campy finds them (yellow dots; cyan marker outlines while an `"auto"` board is still being identified), the parts of the frame where corners have been seen so far (green), how many views the camera saw the board well in, and, for each other camera, in how many frames both saw it: what the cameras' positions are calibrated from. Move the board slowly through every camera's view, near and far, tilted, until each camera's frame is covered and no camera pair reads 0. The view runs in the window's process on the frames it is shown, a few per second and at most half a core, so it never slows the recording; pairs count frames by number, so they are meaningful for cameras on a shared trigger; set `displayDownsample: 1` if the board looks too small to be found.

**3. The recording.** Record into a session folder, with "calibration" in the video's name, and say where calibrat3 is:
```
sessionFolder: True
videoFilename: "calibration.mp4"
calibrate:
  calibrat3: "/path/to/calibrat3"
  runner: "auto" # "node" or "chrome"; auto takes Node when it can
  target: 300 # optional: frames sampled for the board (calibrat3's default otherwise)
```
Before recording, campy says if anything would keep it from calibrating afterwards. When the recording ends, campy writes the board to `board.toml` in the run's folder and calibrates it with calibrat3. It prints each camera's reprojection error and whether the camera made it into the calibration:
```
Calibration: 4 of 4 cameras in calibrations/2026-11-24_14-05-11/calibration.toml (median reprojection error 0.31 px)
  back  median 0.28 px, p95 0.70 px, board in 88 sampled frames: in calibration.toml
  ...
```
**What you get**, in the run's folder: `calibration.toml` (anipose's format: one `[cam_N]` per camera, named as `cameraNames`), `board.toml`, `fit_report.json` (calibrat3's report: each camera's errors, intrinsics, positions) and `fit_log.txt` (what calibrat3 did). If calibration fails, campy says why and the recording stays as it is; you can then open the run's folder in calibrat3's page yourself.

**Using it:** copy `calibration.toml` into a session's run folder, beside its camera folders, and load that folder in LUC3D (Load Session Folder) or sleap-anipose. Keep calibration runs in a `videoFolder` of their own (see above).

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
