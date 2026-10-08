import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import DesignPreview from "./DesignPreview";
import "./index.css";
import "./product-polish.css";

const preview = import.meta.env.DEV && new URLSearchParams(location.search).has("design");
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>{preview ? <DesignPreview /> : <App />}</React.StrictMode>,
);
