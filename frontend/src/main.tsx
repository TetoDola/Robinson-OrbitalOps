import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Theme } from "@astryxdesign/core";

import "@astryxdesign/core/reset.css";
import "@astryxdesign/core/astryx.css";
import App from "./App";
import { orbitopsTheme } from "./theme/orbitopsTheme";
import "./styles/app.css";

const root = document.getElementById("root");

if (!root) {
  throw new Error("Root element #root was not found.");
}

createRoot(root).render(
  <StrictMode>
    <Theme theme={orbitopsTheme} mode="dark">
      <App />
    </Theme>
  </StrictMode>,
);
