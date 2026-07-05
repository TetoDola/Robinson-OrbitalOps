import { create } from "zustand";

export type AppView = "fleet" | "asset";

interface AppStore {
  /** Which level of the two-tier command center is on screen. */
  view: AppView;
  /** The datacenter the asset console is scoped to. */
  selectedAssetId: string;
  openAsset: (id: string) => void;
  goFleet: () => void;
}

export const useAppStore = create<AppStore>((set) => ({
  view: "fleet",
  selectedAssetId: "AKJA-03",
  openAsset: (id) => set({ view: "asset", selectedAssetId: id }),
  goFleet: () => set({ view: "fleet" }),
}));
