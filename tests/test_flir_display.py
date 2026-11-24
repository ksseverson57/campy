"""FLIR display frames, against stand-ins for PySpin 4 (ImageProcessor) and PySpin 2 (Image.Convert)."""

import importlib
import sys
import types
from collections import deque

import numpy as np
import pytest


class FakeImage:
	def __init__(self, array, pixel_format):
		self.array = array
		self.pixel_format = pixel_format
		self.converted = []

	def GetNDArray(self):
		return self.array

	def Convert(self, pixel_format, algorithm):
		# PySpin 2's own conversion; PySpin 4 has no Image.Convert
		self.converted.append((pixel_format, algorithm))
		return FakeImage(Demosaic(self.array), pixel_format)


def Demosaic(array):
	return np.repeat(array[:, :, np.newaxis], 3, axis=2) // 2


def FakePySpin(processor):
	spin = types.ModuleType("PySpin")
	spin.PixelFormat_RGB8 = "RGB8"
	if processor:
		calls = []

		class ImageProcessor:
			def SetColorProcessing(self, algorithm):
				calls.append(("algorithm", algorithm))

			def Convert(self, image, pixel_format):
				calls.append(("convert", pixel_format))
				return FakeImage(Demosaic(image.array), pixel_format)

		spin.ImageProcessor = ImageProcessor
		spin.SPINNAKER_COLOR_PROCESSING_ALGORITHM_HQ_LINEAR = "HQ_LINEAR (processor)"
		spin.calls = calls
	else:
		spin.HQ_LINEAR = "HQ_LINEAR"
	return spin


@pytest.fixture(params=["PySpin 4", "PySpin 2"])
def flir(request, monkeypatch):
	spin = FakePySpin(processor=request.param == "PySpin 4")
	monkeypatch.setitem(sys.modules, "PySpin", spin)
	monkeypatch.delitem(sys.modules, "campy.cameras.flir", raising=False)
	module = importlib.import_module("campy.cameras.flir")
	yield module
	sys.modules.pop("campy.cameras.flir", None)


def frame(height=8, width=10):
	return np.arange(height * width, dtype=np.uint8).reshape(height, width)


def test_mono_frames_need_no_conversion(flir):
	image = FakeImage(frame(), "Mono8")
	queue = deque()
	flir.DisplayImage({"pixelFormatInput": "gray", "displayDownsample": 2}, queue, image)
	[img] = queue
	assert img.shape == (4, 5, 3)
	assert all((img[:, :, c] == frame()[::2, ::2]).all() for c in range(3))
	assert image.converted == [] and getattr(flir.PySpin, "calls", []) == []


def test_bayer_frames_are_demosaiced(flir):
	image = FakeImage(frame(), "BayerRG8")
	queue = deque()
	flir.DisplayImage({"pixelFormatInput": "bayer_rggb8", "displayDownsample": 1}, queue, image)
	[img] = queue
	assert img.shape == (8, 10, 3) and (img == Demosaic(frame())).all()
	if hasattr(flir.PySpin, "ImageProcessor"):
		assert flir.PySpin.calls == [("algorithm", "HQ_LINEAR (processor)"), ("convert", "RGB8")]
		assert image.converted == []
	else:
		assert image.converted == [("RGB8", "HQ_LINEAR")]


def test_one_image_processor_per_process(flir):
	if not hasattr(flir.PySpin, "ImageProcessor"):
		pytest.skip("PySpin 2 has no ImageProcessor")
	for _ in range(3):
		flir.DisplayImage({"pixelFormatInput": "bayer_bggr8", "displayDownsample": 1}, deque(),
			FakeImage(frame(), "BayerRG8"))
	assert [c for c in flir.PySpin.calls if c[0] == "algorithm"] == [("algorithm", "HQ_LINEAR (processor)")]


def test_rgb_frames_pass_through(flir):
	rgb = np.zeros((8, 10, 3), dtype=np.uint8)
	queue = deque()
	flir.DisplayImage({"pixelFormatInput": "rgb24", "displayDownsample": 1}, queue, FakeImage(rgb, "RGB8"))
	assert queue[0] is not None and queue[0].shape == (8, 10, 3)
