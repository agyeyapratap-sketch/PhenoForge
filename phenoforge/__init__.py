"""PhenoForge: open-source 3D plant phenotyping studio for Windows (and Linux/macOS).

The processing core is plain Python (NumPy, SciPy, Open3D, OpenCV) and can be used
without the GUI, from scripts or from the ``phenoforge`` command line.
"""

__version__ = "0.1.0"

from .scan import Scan  # noqa: F401
