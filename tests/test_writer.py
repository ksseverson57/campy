"""The ffmpeg settings campy's writer builds for each encoder (no camera or GPU needed)."""

import pytest

from campy import writer


def Params(**overrides):
	# A camera's settings, with configurator.DefaultParams' compression defaults
	params = {
		"pixelFormatInput": "rgb24",
		"pixelFormatOutput": "rgb0",
		"gpuID": -1,
		"gpuMake": "nvidia",
		"codec": "h264",
		"quality": 21,
		"preset": "None",
		"videoFilename": "0.mp4",
		}
	params.update(overrides)
	return params


def test_cpu_h264():
	codec, pix_fmt, args = writer.EncoderArgs(Params())
	assert codec == "libx264"
	assert pix_fmt == "yuv420p"
	assert args == [
		"-preset", "fast", "-tune", "fastdecode", "-crf", "21",
		"-bufsize", "20M", "-maxrate", "10M", "-bf:v", "4",
		"-x264-params", "nal-hrd=cbr",
		]


def test_cpu_h265():
	codec, pix_fmt, args = writer.EncoderArgs(Params(codec="h265", preset="veryfast"))
	assert codec == "libx265"
	assert args[:2] == ["-preset", "veryfast"]
	assert "-x264-params" not in args


@pytest.mark.parametrize("codec_name, encoder", [("h264", "h264_nvenc"), ("h265", "hevc_nvenc")])
def test_nvenc(codec_name, encoder):
	codec, pix_fmt, args = writer.EncoderArgs(Params(gpuID=1, codec=codec_name, quality=24))
	assert codec == encoder
	assert pix_fmt == "rgb0" # NVENC takes RGB and converts it itself
	assert args == ["-preset", "fast", "-qp", "24", "-bf:v", "0", "-gpu", "1"]


@pytest.mark.parametrize("codec_name, encoder", [("h264", "h264_qsv"), ("h265", "hevc_qsv")])
def test_quick_sync(codec_name, encoder):
	codec, pix_fmt, args = writer.EncoderArgs(Params(gpuID=0, gpuMake="intel", codec=codec_name))
	assert codec == encoder
	assert pix_fmt == "nv12"
	assert args == ["-bf:v", "0", "-preset", "faster", "-q", "22"]


@pytest.mark.parametrize("pix_fmt_out", ["rgb0", "bgr0", "yuv420p"])
def test_quick_sync_gets_nv12(pix_fmt_out):
	# Quick Sync takes 8-bit video as NV12 only; asked for yuv420p, ffmpeg
	# would switch to NV12 itself, with a warning
	codec, pix_fmt, args = writer.EncoderArgs(Params(gpuID=0, gpuMake="intel", pixelFormatOutput=pix_fmt_out))
	assert pix_fmt == "nv12"


@pytest.mark.parametrize("gpu", [dict(gpuID=-1), dict(gpuID=0, gpuMake="amd")])
def test_yuv420p_kept_elsewhere(gpu):
	codec, pix_fmt, args = writer.EncoderArgs(Params(pixelFormatOutput="yuv420p", **gpu))
	assert pix_fmt == "yuv420p"


@pytest.mark.parametrize("codec_name, encoder", [("h264", "h264_amf"), ("h265", "hevc_amf")])
def test_amf(codec_name, encoder):
	codec, pix_fmt, args = writer.EncoderArgs(Params(gpuID=0, gpuMake="amd", codec=codec_name))
	assert codec == encoder
	assert pix_fmt == "yuv420p"
	assert args == [
		"-usage", "lowlatency", "-rc", "cqp",
		"-qp_i", "21", "-qp_p", "21", "-qp_b", "21",
		"-bf:v", "0",
		]
	# -hwaccel_device is an input option: ffmpeg refuses it among the output
	# options, and the camera's writer could not start
	assert "-hwaccel_device" not in args
