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


@pytest.mark.parametrize("gpu, encoder", [
	(dict(gpuID=-1), "libx265"),
	(dict(gpuID=0, gpuMake="nvidia"), "hevc_nvenc"),
	(dict(gpuID=0, gpuMake="intel"), "hevc_qsv"),
	(dict(gpuID=0, gpuMake="amd"), "hevc_amf"),
	])
def test_mac_compatible_h265(gpu, encoder):
	plain = writer.EncoderArgs(Params(codec="h265", **gpu))
	codec, pix_fmt, args = writer.EncoderArgs(Params(codec="h265", macCompatibleH265=True, **gpu))
	assert codec == encoder
	added = ["-x265-params", "open-gop=0"] if encoder == "libx265" else []
	assert args == plain[2] + added + ["-tag:v", "hvc1"]


def test_mac_compatible_h265_off_by_default():
	# An existing config records exactly as before
	for gpu in [dict(gpuID=-1), dict(gpuID=0, gpuMake="nvidia"), dict(gpuID=0, gpuMake="intel")]:
		codec, pix_fmt, args = writer.EncoderArgs(Params(codec="h265", **gpu))
		assert "-tag:v" not in args and "-x265-params" not in args


@pytest.mark.parametrize("filename, tagged", [("0.mp4", True), ("0.MOV", True), ("0.mkv", False)])
def test_mac_compatible_h265_containers(filename, tagged):
	# hvc1 is an MP4/MOV tag; other containers are left as they are
	codec, pix_fmt, args = writer.EncoderArgs(Params(codec="h265", macCompatibleH265=True, videoFilename=filename))
	assert ("-tag:v" in args) == tagged


def test_mac_compatible_h265_leaves_h264_alone():
	assert writer.EncoderArgs(Params(macCompatibleH265=True)) == writer.EncoderArgs(Params())


# AV1 on each GPU: the encoder, and quality as AV1's quantizer index (0-255)
AV1_ENCODERS = [
	("nvidia", "av1_nvenc", "rgb0", ["-preset", "fast", "-qp", "88", "-bf:v", "0", "-gpu", "0"]),
	("intel", "av1_qsv", "nv12", ["-bf:v", "0", "-preset", "faster", "-q", "88"]),
	("amd", "av1_amf", "yuv420p", ["-usage", "lowlatency", "-rc", "cqp",
		"-qp_i", "88", "-qp_p", "88", "-qp_b", "88", "-bf:v", "0"]),
	]


@pytest.mark.parametrize("gpu_make, encoder, pix_fmt_out, expected", AV1_ENCODERS)
def test_av1_on_gpu(gpu_make, encoder, pix_fmt_out, expected):
	codec, pix_fmt, args = writer.EncoderArgs(Params(gpuID=0, gpuMake=gpu_make, codec="av1", quality=88))
	assert codec == encoder
	assert pix_fmt == pix_fmt_out
	assert args == expected


@pytest.mark.parametrize("gpu_make", ["nvidia", "intel", "amd"])
def test_av1_only_changes_the_encoder_name_and_quality(gpu_make):
	# AV1 takes the same options as H.265 on each GPU; only Quick Sync's
	# quality differs (H.265's is quality + 1)
	h265 = writer.EncoderArgs(Params(gpuID=0, gpuMake=gpu_make, codec="h265", quality=30))
	av1 = writer.EncoderArgs(Params(gpuID=0, gpuMake=gpu_make, codec="av1", quality=30))
	assert av1[1:] == (h265[1], [("30" if a == "31" else a) for a in h265[2]])


def test_av1_on_cpu_is_refused():
	# ffmpeg's own choice for "av1" (libaom-av1) would refuse campy's CPU options
	with pytest.raises(ValueError, match="GPU only"):
		writer.EncoderArgs(Params(codec="av1"))


def test_unmapped_codec_on_gpu_warns(caplog):
	# "hevc" is passed to ffmpeg as it is, which then picks libx265, on the CPU
	codec, pix_fmt, args = writer.EncoderArgs(Params(gpuID=0, gpuMake="intel", codec="hevc"))
	assert codec == "hevc"
	assert "may run on the CPU" in caplog.text


@pytest.mark.parametrize("gpu_make", ["nvidia", "intel", "amd"])
@pytest.mark.parametrize("codec_name", ["h264", "h265", "av1"])
def test_mapped_codecs_do_not_warn(caplog, gpu_make, codec_name):
	writer.EncoderArgs(Params(gpuID=0, gpuMake=gpu_make, codec=codec_name))
	assert caplog.text == ""


def test_av1_leaves_mac_compatible_h265_alone():
	codec, pix_fmt, args = writer.EncoderArgs(Params(gpuID=0, codec="av1", macCompatibleH265=True))
	assert "-tag:v" not in args
