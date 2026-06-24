import { BrowserRouter, Routes, Route } from "react-router-dom";
import Home from "./journey/Home";
import Single from "./journey/Single";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/story/:slug" element={<Single />} />
      </Routes>
    </BrowserRouter>
  );
}
