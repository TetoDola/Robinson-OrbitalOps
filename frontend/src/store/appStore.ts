import { create } from "zustand";

export type AppView = "fleet" | "asset";

interface AppStore {
  view: AppView;
  selectedAssetId: string;
  /** Fleet view: chat panel open for a satellite. */
  fleetChatAssetId: string | null;
  openAsset: (id: string) => void;
  goFleet: () => void;
  openFleetChat: (id: string) => void;
  closeFleetChat: () => void;
}

export const useAppStore = create<AppStore>((set) => ({
  view: "fleet",
  selectedAssetId: "AKJA-03",
  fleetChatAssetId: null,
  openAsset: (id) => set({ view: "asset", selectedAssetId: id, fleetChatAssetId: null }),
  goFleet: () => set({ view: "fleet", fleetChatAssetId: null }),
  openFleetChat: (id) => set({ fleetChatAssetId: id, selectedAssetId: id }),
  closeFleetChat: () => set({ fleetChatAssetId: null }),
}));
