import { BrowserRouter, Routes, Route } from "react-router-dom";
import Journey from "./journey/Journey";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Journey />} />
        <Route path="/story/:slug" element={<Journey />} />
      </Routes>
    </BrowserRouter>
  );
}
