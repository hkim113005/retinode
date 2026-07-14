"""Units, sign conventions, and tolerances — fixed once, asserted in tests.

Retinode pins these conventions everywhere so that a whole class of stimulation
bugs (unit and sign errors) cannot occur silently:

    length        micrometers (um)      field names carry the unit, e.g. pos_um
    current        microamps (uA)        signed: cathodic (excitatory) current is NEGATIVE
    conductivity   siemens / meter (S/m)
    time           microseconds (us)     waveform phase widths
    potential      millivolts (mV)       at the cable layer (NEURON extracellular)

Units are encoded in field names rather than tracked at runtime, so the type
system and code review enforce them. See docs/retinode-project-plan-revised.md §5.
"""

# Bumped when a spec object's on-disk shape changes, so old projects migrate
# forward instead of failing silently. Every top-level spec object carries it.
SCHEMA_VERSION = 1

# A biphasic stimulus whose return current flows on-array must charge-balance:
# the signed relative weights sum to ~0. Compared with this absolute tolerance.
CHARGE_BALANCE_ATOL = 1e-9

# Two electrodes are considered overlapping if their centers are closer than
# this (used by geometry validation).
GEOMETRY_OVERLAP_ATOL_UM = 1e-6
