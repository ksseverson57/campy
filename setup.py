from setuptools import setup, find_packages

setup(
	name='campy',
	version='1.0.0',
	packages=find_packages(),
	install_requires=[
					'numpy',
					'imageio',
					'imageio-ffmpeg',
					'scikit-image',
					'pyyaml',
					],
	entry_points={
		"console_scripts": [
			"campy-acquire = campy.campy:Main"
		]
	}
)