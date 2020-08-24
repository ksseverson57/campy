class CampyParams():
    videoFolder: "./test"
    camSettings: "./settings/acA1920-150uc_1152x1024p_100fps_trigger_RGB_p6.pfs"
    frameRate: 100
    recTimeInSec: 10

    # Camera parameters
    cameraMake: 'basler'
    numCams: 6
    cameraNames: ['Camera1','Camera2','Camera3','Camera4','Camera5','Camera6']

    # Compression parameters
    gpus: [0,0,0,2,2,2]
    pixelFormatInput: 'rgb24' # 'bayer_bggr8' 'rgb24'
    pixelFormatOutput: 'rgb0'
    quality: '21'

    # Display parameters
    chunkLengthInSec: 30
    displayFrameRate: 10
    displayDownsample: 2
