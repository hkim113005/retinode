"""Scene translation and view payloads over the engine.

Strict boundary (project plan §4): ``app`` imports ``engine``, never the reverse.

This package used to hold the Dash dashboard; that UI was retired in P7 S8 once
the React client (``app/web``) reached parity. What remains is load-bearing and
has nothing to do with Dash:

- ``scene`` — pure translation of UI state into spec objects. The API imports it
  (``api.routes``, ``api.fem_job``); it is not optional.
- ``views`` — pure view payloads, kept as the API's independent oracle
  (``tests/api/test_compare`` asserts the endpoints agree with them).
- ``validation_report.json`` — the committed reproductions report CI regenerates
  and ``GET /validation`` serves.
- ``web/`` — the React client.
"""
