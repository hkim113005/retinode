# Mechanisms provenance

## Source
- **Fohlmeister–Miller RGC channels**, ModelDB accession **#3673**
  (<https://modeldb.science/3673>, mirror <https://github.com/ModelDBRepository/3673>),
  files `spike.mod` and `capump.mod`, retrieved 2026-07-14 from branch `master`.
- Model: HH-style spiking retinal ganglion cell channels (fast Na `m`,`h`;
  delayed-rectifier K `n`; A-type K `p`,`q`; Ca `c`; and Ca-activated K), plus a
  submembrane calcium-decay mechanism (`cad`). Implemented for NEURON by
  T. J. Velte (1995), after Fohlmeister et al. 1990; see Fohlmeister & Miller 1997.

## License
**No explicit license file accompanies the ModelDB entry.** ModelDB code is published
for research reuse, but the absence of stated terms means the redistribution rights are
not defined by the authors.

These files are therefore **not covered by this project's MIT license**, which grants
rights the project cannot grant over someone else's work. See the `NOTICE` file at the
repository root, which scopes the MIT grant to first-party code and records these
components separately.

`capump.mod` is vendored verbatim. `spike.mod` is vendored **with one documented
modification** (the q10 temperature scaling below), so it is a derivative work and is
redistributed on the same unstated terms as the original.

Cite Fohlmeister & Miller (1997) and ModelDB #3673.

## Modifications
- **`capump.mod`: none.**
- **`spike.mod`: added q10 temperature scaling (2026-07-14).** The salamander
  FM/Velte rate equations carry no temperature dependence, so mammalian (37 °C)
  behaviour requires it (Fohlmeister 2010). Added `PARAMETER q10 (=2.5), temp0
  (=22)`; in `evaluate_fct` each gating tau is divided by
  `tadj = q10^((celsius − temp0)/10)`. No kinetics or topology otherwise changed,
  and at `celsius = temp0` the model reduces exactly to the original. Verified:
  `tau_m` speeds up 3.95× from 22 °C to 37 °C (= 2.5^1.5).
  This modification is what makes `spike.mod` a derivative work; see **License** above.
- Both files compile as-is on **NEURON 9.0.1** (C++ toolchain), with only benign
  warnings: VERBATIM not thread-safe; "cannot be used with CVODE" (we use fixed
  `dt` by design); PARAMETER reversal-potential defaults overridden by NEURON.

## Species and temperature: the FM-2010 adaptation is applied at insertion
These are the salamander-derived FM/Velte rate equations with **no temperature
scaling**. Retinode targets *mammalian* RGCs, so the **Fohlmeister-2010 mammalian**
adaptation (a q10 temperature correction to 37 °C plus per-region conductance
densities) is applied when channels are inserted (`engine/cable/channels.py`,
step S2c) and calibrated against Greenberg 1999 / Tsai 2012 (S5). The morphology is
likewise a mammalian reconstruction, specifically **mouse** (see
`engine/cable/morphologies/PROVENANCE.md`), so cell and channels are the same species
class. See `docs/phase-1-plan.md`.

## References
- Fohlmeister JF, Miller RF. "Impulse encoding mechanisms of ganglion cells in
  the tiger salamander retina." *J Neurophysiol* 78(4):1935–1947, 1997.
- Fohlmeister JF, Cohen ED, Newman EA. "Mechanisms and distribution of ion
  channels in retinal ganglion cells: using temperature as an independent
  variable." *J Neurophysiol* 103, 2010. (mammalian; temperature/q10)
- Velte TJ, 1995. NEURON implementation, ModelDB #3673.
