import { useState } from "react";
import { House } from "lucide-react";

/** Generated concept artwork never represents the assessed home's facts. */
export function HeroScene() {
  const [failed, setFailed] = useState(false);
  return (
    <figure className="hero-figure conceptual-home generated-home">
      {failed ? (
        <div className="house-image-fallback">
          <House size={44} strokeWidth={1.25} aria-hidden="true" />
          <span>House illustration unavailable</span>
        </div>
      ) : (
        <img
          src="/assets/home-concept-chatgpt.webp"
          srcSet="/assets/home-concept-chatgpt-small.webp 640w, /assets/home-concept-chatgpt.webp 1200w"
          sizes="(max-width: 700px) calc(100vw - 40px), (max-width: 950px) 380px, 34vw"
          width={1200}
          height={675}
          alt="AI-generated illustration of two adjoining British houses, not the assessed property"
          loading="eager"
          fetchPriority="high"
          decoding="async"
          onError={() => setFailed(true)}
        />
      )}
      <figcaption>
        AI-generated concept · not the assessed property or evidence of
        installed improvements
      </figcaption>
    </figure>
  );
}
