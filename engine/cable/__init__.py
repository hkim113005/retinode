"""Cable and population engine.

Only the pure activating-function diagnostic is present so far; the NEURON-backed
morphology, drive, spike detection, threshold search, and population runner land
in S2-S6. Importing this package does not import NEURON.
"""

from .activating import activating_function

__all__ = ["activating_function"]
