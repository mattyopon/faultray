// FaultRay Chrome Extension — Popup entry point
import { createRoot } from "react-dom/client";
import { Popup } from "./Popup";

const rootEl = document.getElementById("root");
if (!rootEl) throw new Error("Root element #root not found");

createRoot(rootEl).render(<Popup />);
