import React from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import App from "./App.jsx";
import Roster from "./routes/Roster.jsx";
import Console from "./routes/Console.jsx";
import ModelDetail from "./routes/ModelDetail.jsx";
import Train from "./routes/Train.jsx";
import "./styles.css";

const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Roster /> },
      { path: "new", element: <Console /> },
      { path: "model/:slug", element: <ModelDetail /> },
      { path: "model/:slug/train", element: <Train /> },
    ],
  },
]);

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>
);
