import { useParams } from "react-router-dom";

export default function Single() {
  const { slug } = useParams();
  return <div><span data-testid="single-slug">{slug}</span></div>;
}
