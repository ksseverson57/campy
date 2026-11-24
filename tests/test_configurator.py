"""campy's config: the new key's default, and setting it in config.yaml or on the command line."""

import sys

from campy import configurator


def Configure(monkeypatch, tmp_path, yaml_text, *args):
	config = tmp_path / "config.yaml"
	config.write_text(yaml_text)
	monkeypatch.setattr(sys, "argv", ["campy-acquire", str(config)] + list(args))
	monkeypatch.delenv("IMAGEIO_FFMPEG_EXE", raising=False)
	return configurator.ConfigureParams()


def test_mac_compatible_h265_defaults_off(monkeypatch, tmp_path):
	params = Configure(monkeypatch, tmp_path, 'numCams: 1\ncodec: "h265"\n')
	assert params["macCompatibleH265"] is False


def test_mac_compatible_h265_from_config(monkeypatch, tmp_path):
	params = Configure(monkeypatch, tmp_path, 'numCams: 1\ncodec: "h265"\nmacCompatibleH265: True\n')
	assert params["macCompatibleH265"] is True


def test_mac_compatible_h265_from_command_line(monkeypatch, tmp_path):
	params = Configure(monkeypatch, tmp_path, 'numCams: 1\n', "--macCompatibleH265", "True")
	assert params["macCompatibleH265"] is True
	params = Configure(monkeypatch, tmp_path, 'numCams: 1\nmacCompatibleH265: True\n', "--macCompatibleH265", "False")
	assert params["macCompatibleH265"] is False
