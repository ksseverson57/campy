from setuptools import setup, find_packages

setup(
	name='campy',
	version='0.2.0',
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
            "campy-acquire = campy.campy:main"
        ]
    }
)