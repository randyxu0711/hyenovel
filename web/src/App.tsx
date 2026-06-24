import { BrowserRouter, Routes, Route } from "react-router-dom";
import Overview from "./journey/Overview";
import Single from "./journey/Single";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/story/:slug" element={<Single />} />
      </Routes>
    </BrowserRouter>
  );
}
