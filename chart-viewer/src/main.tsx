import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";
// @ts-expect-error included by recommendation of https://vite.dev/guide/backend-integration.html
import "vite/modulepreload-polyfill";

const simfileURL = document.getElementById("root")!.dataset.simfileUrl!;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App simfileURL={simfileURL} />
  </StrictMode>
);
