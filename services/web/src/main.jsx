import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import HostedSession from "./HostedSession.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <HostedSession><App /></HostedSession>
  </React.StrictMode>,
);
