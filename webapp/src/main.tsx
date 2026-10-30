import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

// Telegram SDK must be told the app is ready, otherwise the window
// stays half-height inside Telegram. Outside Telegram (plain browser
// testing) `window.Telegram` is undefined — optional chaining keeps it safe.
const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();
tg?.setHeaderColor?.("#1D4ED8");
tg?.setBackgroundColor?.("#EFF6FF");

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
