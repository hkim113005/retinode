"""The Retinode dashboard: a thin Dash/Plotly app over the engine (Phase 2b).

Strict boundary (project plan §4): ``app`` imports ``engine``, never the reverse.
The app only *drives* the engine and renders its outputs — all science lives in
``engine``. Everything here is either a pure translation of UI state into spec
objects (``scene``), a pure view payload / figure (``views``), or Dash wiring
(``ui``).
"""
