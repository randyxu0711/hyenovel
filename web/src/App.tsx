import { BrowserRouter, Routes, Route } from "react-router-dom";
import Journey from "./journey/Journey";
import Lab from "./lab/Lab";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Journey />} />
        <Route path="/story/:slug" element={<Journey />} />
        <Route path="/lab" element={<Lab />} />
      </Routes>
    </BrowserRouter>
  );
}
