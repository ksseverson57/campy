import os

# Qt windows in the tests are drawn off screen: no display needed
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
