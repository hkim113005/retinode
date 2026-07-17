import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// globals are off (see vite.config), so register RTL's DOM cleanup explicitly —
// without it, renders leak between tests and elements appear duplicated.
afterEach(cleanup);
