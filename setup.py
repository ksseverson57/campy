from setuptools import setup, find_packages

setup(
	name='campy',
	version='2.0.1',
	packages=find_packages(),
	install_requires=[
					'imageio',
					'matplotlib',
					'numpy',
					'pyserial',
					'pyyaml',
					'scikit-image',
					],
	entry_points={
		"console_scripts": [
			"campy-acquire = campy.campy:Main"
		]
	}
)