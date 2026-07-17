import { MotionConfig } from "framer-motion";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Journey from "./journey/Journey";
import Lab from "./lab/Lab";
import BornLab from "./lab/BornLab";

export default function App() {
  return (
    // reducedMotion="user":減動偏好下 framer-motion 自動把 transform/scale/blur 動畫瞬切(Camera 運鏡、Overview 淡入一併守)
    <MotionConfig reducedMotion="user">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Journey />} />
          <Route path="/story/:slug" element={<Journey />} />
          <Route path="/lab" element={<Lab />} />
          <Route path="/lab/born" element={<BornLab />} />
        </Routes>
      </BrowserRouter>
    </MotionConfig>
  );
}
