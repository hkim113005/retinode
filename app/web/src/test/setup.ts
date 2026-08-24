import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// globals are off (see vite.config), so register RTL's DOM cleanup explicitly.
// Without it, renders leak between tests and elements appear duplicated.
afterEach(cleanup);

// jsdom has no WebGL, so stub the react-three-fiber canvas globally: the 3D loupe
// renders its chrome (label, expand button) but no GL scene during tests. It is
// exercised for real in the browser.
vi.mock("@react-three/fiber", () => ({ Canvas: () => null }));
vi.mock("@react-three/drei", () => ({ OrbitControls: () => null }));
