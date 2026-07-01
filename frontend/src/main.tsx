import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AdminProvider } from "./context/AdminContext";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AdminProvider>
        <App />
      </AdminProvider>
    </BrowserRouter>
  </StrictMode>,
);
