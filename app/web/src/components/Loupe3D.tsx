// The 3D loupe (docs/phase-7-design.md): a small, always-available corner view of
// the array's true 3D form — the tissue slab, the electrodes on the array plane, and
// the cell population at depth — orbitable, secondary to the 2D field. Click to
// expand full-bleed. Rendered with react-three-fiber; lazy-loaded so three.js stays
// off the main chunk.
//
// Scope: this draws each electrode's true solid when the marker carries a body
// (ElectrodeMarker.body — a pillar, dome, taper, or a CAD solid's bounding cylinder),
// and a flat disk otherwise. Array tilt/rotation is still not represented (the marker
// has no orientation); a tilted body draws upright. The body is schematic — lateral
// and depth share one scale so proportions read true, but the whole view exaggerates
// the ~20 µm layer separation so the cell plane is legible.
import { OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useState } from "react";
import type { CellMarker, ElectrodeMarker } from "../api/client";

// The auto-spin is a rAF render loop, not a CSS animation, so the global
// reduced-motion rule in tokens.css can't reach it — honour the OS setting here.
const prefersReducedMotion = () =>
  typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;

const CELL_DEPTH = 20; // µm below the array plane (matches app.scene)

function cssVar(n: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(n).trim() || "#888888";
}

function Scene({
  electrodes,
  cells,
  inked,
  active,
}: {
  electrodes: ElectrodeMarker[];
  cells: CellMarker[];
  inked: boolean;
  active: boolean;
}) {
  const field = cssVar("--field");
  const warm = cssVar("--warm");
  const ink = cssVar("--canvas-ink");
  const accent = cssVar("--accent-strong");
  // fit the view to the geometry: half-extent maps to ~2.2 units, so the electrodes
  // and cells fill the frame instead of being specks in the full field.
  const reach = Math.max(
    45,
    ...electrodes.map((e) => Math.hypot(e.x_um, e.y_um) + e.radius_um),
    ...cells.map((c) => Math.hypot(c.x_um, c.y_um)),
  );
  const LAT = 2.2 / (reach + 15);
  const DEPTH = LAT * 5; // exaggerate depth so the ~20 µm layer separation reads
  const EL = LAT * 4; // electrode lateral+depth scale — a body draws at true aspect
  const grid = 2.4 * reach * LAT;
  const slabH = (CELL_DEPTH + 10) * DEPTH;
  return (
    <>
      <ambientLight intensity={0.85} />
      <directionalLight position={[6, 14, 8]} intensity={0.9} />
      <pointLight position={[0, 3, 0]} intensity={18} distance={12} color={field} />
      {/* tissue slab: from the array plane (y=0) down into the tissue */}
      <mesh position={[0, -slabH / 2, 0]}>
        <boxGeometry args={[grid, slabH, grid]} />
        <meshStandardMaterial
          color={field}
          transparent
          opacity={inked ? 0.18 : 0.12}
          depthWrite={false}
        />
      </mesh>
      {/* the array plane at the top of the tissue */}
      <gridHelper args={[grid, 10, accent, accent]} position={[0, 0.02, 0]} />
      {/* electrodes: metal, lit to read against the slab. A body protrudes DOWN into
          the tissue (−y = +z into tissue); a flat electrode is a thin disk on the plane. */}
      {electrodes.map((e, i) => {
        const b = e.body;
        // Key on the SHAPE, not just the index. Switching Flat -> Pillar keeps the
        // same <mesh> element in the same slot and only changes <cylinderGeometry
        // args>, which relies on r3f rebuilding the geometry object in place; keying
        // by shape remounts instead, so the new solid cannot be missed. (The mesh has
        // no test coverage — the Canvas is stubbed in jsdom — so this path is belt
        // and braces rather than a reproduced fix.)
        const shapeKey = b ? `${b.kind}:${b.radius_um}:${b.height_um}:${b.top_radius_um ?? ""}` : "flat";
        const mat = (
          <meshStandardMaterial
            color={ink}
            metalness={0.6}
            roughness={0.3}
            emissive={ink}
            emissiveIntensity={0.15}
          />
        );
        if (!b) {
          return (
            <mesh key={`e${i}-${shapeKey}`} position={[e.x_um * LAT, 0.2, e.y_um * LAT]}>
              <cylinderGeometry args={[e.radius_um * EL, e.radius_um * EL, 0.4, 28]} />
              {mat}
            </mesh>
          );
        }
        if (b.kind === "hemisphere") {
          // lower half-sphere: a dome pushing into the tissue from the plane
          return (
            <mesh key={`e${i}-${shapeKey}`} position={[e.x_um * LAT, 0, e.y_um * LAT]}>
              <sphereGeometry args={[b.radius_um * EL, 24, 16, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2]} />
              {mat}
            </mesh>
          );
        }
        // cylinder / frustum / cad(bounding): a (possibly tapered) column, base at the
        // plane (+y) tapering to the tip at depth (−y). cylinderGeometry(top, bottom, h).
        const h = b.height_um * EL;
        const rBase = b.radius_um * EL;
        const rTip = b.kind === "frustum" && b.top_radius_um != null ? b.top_radius_um * EL : rBase;
        return (
          <mesh key={`e${i}-${shapeKey}`} position={[e.x_um * LAT, -h / 2, e.y_um * LAT]}>
            <cylinderGeometry args={[rBase, rTip, h, 28]} />
            {mat}
          </mesh>
        );
      })}
      {/* cell somata at depth: target filled + glowing, off-target muted blue */}
      {cells.map((c, i) => (
        <mesh key={`c${i}`} position={[c.x_um * LAT, -CELL_DEPTH * DEPTH, c.y_um * LAT]}>
          <sphereGeometry args={[c.is_target ? 0.55 : 0.42, 20, 20]} />
          <meshStandardMaterial
            color={c.is_target ? warm : field}
            emissive={c.is_target ? warm : field}
            emissiveIntensity={c.is_target ? 0.6 : 0.25}
          />
        </mesh>
      ))}
      {/* the corner inset just spins; the expanded view is fully orbitable */}
      <OrbitControls
        target={[0, -CELL_DEPTH * DEPTH * 0.6, 0]}
        enablePan={false}
        enableZoom={active}
        enableRotate={active}
        autoRotate={!active && !prefersReducedMotion()}
        autoRotateSpeed={0.8}
      />
    </>
  );
}

export default function Loupe3D({
  electrodes,
  cells,
  tier = "analytical",
  bodyKind,
}: {
  electrodes: ElectrodeMarker[];
  cells: CellMarker[];
  tier?: "analytical" | "fem";
  // What the user actually selected. /compare cannot send a marker body for a CAD
  // solid — reading it needs gmsh, which lives in the FEM env — so the marker comes
  // back bodyless and the loupe would draw, and caption, a flat disk. Drawing the
  // wrong shape is bad; calling it "flat disk" is worse, because that is a claim.
  bodyKind?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  // Name the solid being drawn. The 3D view is WebGL, so when it is wrong (or blank)
  // there is nothing to read; this caption says in text what the loupe was handed, so
  // a stale or missing body is visible without a working canvas.
  const b0 = electrodes[0]?.body;
  const drawn = !b0 && bodyKind === "cad"
    ? "CAD solid \u2014 shape needs FEM"
    : !b0
    ? "flat disk"
    : b0.kind === "hemisphere"
      ? `dome r${b0.radius_um}`
      : b0.kind === "frustum"
        ? `taper ${b0.radius_um}\u2192${b0.top_radius_um ?? "?"} \u00d7 ${b0.height_um}`
        : `${b0.kind === "cad" ? "CAD" : "pillar"} r${b0.radius_um} \u00d7 ${b0.height_um}`;
  const scene = (active: boolean) => (
    <Canvas camera={{ position: [3.4, 4.8, 5.2], fov: 42 }} dpr={[1, 2]} gl={{ alpha: true }}>
      <Scene electrodes={electrodes} cells={cells} inked={tier === "fem"} active={active} />
    </Canvas>
  );

  if (expanded) {
    return (
      <div className="loupe-overlay" role="dialog" aria-label="Array in 3D">
        <div className="loupe-expanded card">
          <div className="loupe-head">
            <span className="lab">Array · 3D · tissue &amp; cells · {drawn}</span>
            <button className="btn small" onClick={() => setExpanded(false)}>
              Close
            </button>
          </div>
          <div className="loupe-canvas big">{scene(true)}</div>
        </div>
      </div>
    );
  }
  return (
    <div className="loupe card">
      <span className="lab">Array · 3D · {drawn}</span>
      <button
        className="loupe-expand"
        onClick={() => setExpanded(true)}
        aria-label="Expand the 3D array view"
        title="Expand"
      >
        ⤢
      </button>
      <div className="loupe-canvas">{scene(false)}</div>
    </div>
  );
}
