import pytest

from campy import startup


@pytest.fixture(autouse=True)
def forget_the_camera():
	# Each camera process holds one camera's startup lines; tests record several in one process
	startup.Reset()
	yield
	startup.Reset()
