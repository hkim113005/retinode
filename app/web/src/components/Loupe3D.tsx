// The 3D loupe (docs/phase-7-design.md): a small, always-available corner view of
// the array's true 3D form — the tissue slab, the electrodes on the array plane, and
// the cell population at depth — orbitable, secondary to the 2D field. Click to
// expand full-bleed. Rendered with react-three-fiber; lazy-loaded so three.js stays
// off the main chunk.
//
// Scope, precisely: this draws FLAT DISKS ONLY. Phase 6 gave the engine 3D bodies,
// array tilt, CAD import and overlap flags — none of which can reach here, because
// the view contract is flat (ElectrodeMarker is x/y/radius; no z, no rotation, no
// body). That is a contract gap, not a dormant code path: there is no body-rendering
// code below, and none could be triggered if there were. Drawing them needs the
// contract to carry them and an authoring surface to set them (see docs/phase-8).
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
      {/* electrodes: metal disks on the plane, lit so they read against the slab */}
      {electrodes.map((e, i) => (
        <mesh key={`e${i}`} position={[e.x_um * LAT, 0.2, e.y_um * LAT]}>
          <cylinderGeometry args={[e.radius_um * LAT * 4, e.radius_um * LAT * 4, 0.4, 28]} />
          <meshStandardMaterial color={ink} metalness={0.6} roughness={0.3} emissive={ink} emissiveIntensity={0.15} />
        </mesh>
      ))}
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
}: {
  electrodes: ElectrodeMarker[];
  cells: CellMarker[];
  tier?: "analytical" | "fem";
}) {
  const [expanded, setExpanded] = useState(false);
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
            <span className="lab">Array · 3D · tissue &amp; cells</span>
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
      <span className="lab">Array · 3D</span>
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
