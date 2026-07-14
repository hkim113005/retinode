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

## Species decision — mouse chosen over cat/rat (recorded 2026-07-14)
Cat/rat were the originally preferred species (they match the FM-2010 rat/cat
channels). NeuroMorpho was searched again and **mouse was chosen deliberately**:

- **Cat:** no retinal ganglion reconstructions available.
- **Rat:** ~372 available, but every usable option is worse for this tool's
  purpose — the only "Dendrites Complete" rat cell (Bohlen archive) has **no soma
  node** and ~9151 dendrite points (unusable); the clean rat cells (Rodger LY8
  series) are only **"Dendrites Moderate"** (truncated arbor).
- **Mouse (this file):** "Dendrites Complete" + proper soma + planar arbor.

**Deciding factor: threshold accuracy.** The 2023 review shows truncated
dendrites bias extracellular-stimulation thresholds, so complete dendrites beat
an exact species match — especially since the channels are rat/cat regardless of
morphology, mouse/rat RGC dendrites are morphologically similar, and the real
target (primate) is a mammalian proxy either way. Primate-specificity is
captured at the array/patch scale, not the single cell.

**Reversible** via the `cell_type -> template` registry in
`engine/cable/morphology.py`; revisit only if arbor sim cost bottlenecks S4/S6.

## Modifications
- **None to the file.** Comment/header lines are stripped in memory before
  NEURON's Import3D reads it (Import3D emits benign warnings on the CNG comment
  block otherwise); the coordinate/topology data is used verbatim.
