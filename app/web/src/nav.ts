// The analysis screens the rail navigates between (the Design steps are later slices).
export const SCREENS = ["Compare", "Study", "Validation", "Candidates"] as const;

export type Screen = (typeof SCREENS)[number];
