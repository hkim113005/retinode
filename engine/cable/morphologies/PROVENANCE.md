# Morphologies provenance

## `20160506-P21-control38-1.CNG.swc`
- **Source:** NeuroMorpho.org, neuron `20160506-P21-control38-1` (id 105516),
  standardized CNG version, retrieved 2026-07-14.
- **Cell:** mouse (P21) **retinal ganglion cell**, brain region retina,
  reconstruction integrity "Dendrites Complete" (1514 dendrite points, a
  3-point soma ~22.7 µm; planar arbor ~260 × 360 µm, ~12 µm thick). No axon is
  traced — the AIS/sodium-band and intraretinal axon are appended by
  `engine/cable/morphology.py` along the spec's `axon_um` path.
- **Archive:** Wang.
- **Reference:** Wang et al., *Neuroscience Letters* 2018,
  doi:10.1016/j.neulet.2018.04.012 (PMID 29627341).
- **Citation:** please cite NeuroMorpho.org and the source publication above.

## Species note
Mouse is used because well-reconstructed **mammalian** RGC arbors are abundant on
NeuroMorpho while primate/cat/rat retinal reconstructions are scarce; mouse is
consistent with the mammalian FM-2010 (rat/cat) channels at the mammalian level.
Primate-specificity is captured at the array/patch scale, not the single-cell
morphology. See `docs/phase-1-plan.md`.

## Modifications
- **None to the file.** Comment/header lines are stripped in memory before
  NEURON's Import3D reads it (Import3D emits benign warnings on the CNG comment
  block otherwise); the coordinate/topology data is used verbatim.
