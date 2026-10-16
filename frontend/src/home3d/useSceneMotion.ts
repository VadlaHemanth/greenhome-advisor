import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type RefObject,
} from "react";

/** One bounded CSS animation + one timeout, never a continuously scheduled frame. */
export function useSceneMotion(
  root: RefObject<HTMLElement | null>,
  proposalKey: string,
) {
  const [animating, setAnimating] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reduced = useRef(true);
  const visible = useRef(true);
  const lastKey = useRef(proposalKey);
  const stop = useCallback(() => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
    setAnimating(false);
  }, []);
  const play = useCallback(() => {
    if (reduced.current || !visible.current || document.hidden) return;
    if (timer.current !== null) clearTimeout(timer.current);
    setAnimating(true);
    timer.current = setTimeout(() => {
      timer.current = null;
      setAnimating(false);
    }, 1200);
  }, []);
  useEffect(() => {
    const query = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    reduced.current = query?.matches ?? true;
    const onMotion = (event: MediaQueryListEvent) => {
      reduced.current = event.matches;
      if (event.matches) stop();
    };
    const onVisibility = () => {
      if (document.hidden) stop();
    };
    query?.addEventListener("change", onMotion);
    document.addEventListener("visibilitychange", onVisibility);
    const observer =
      typeof IntersectionObserver === "undefined"
        ? null
        : new IntersectionObserver(([entry]) => {
            visible.current = entry.isIntersecting;
            if (!entry.isIntersecting) stop();
          });
    if (root.current) observer?.observe(root.current);
    return () => {
      if (timer.current !== null) clearTimeout(timer.current);
      timer.current = null;
      query?.removeEventListener("change", onMotion);
      document.removeEventListener("visibilitychange", onVisibility);
      observer?.disconnect();
    };
  }, [root, stop]);
  useEffect(() => {
    if (lastKey.current === proposalKey) return;
    lastKey.current = proposalKey;
    stop();
    if (proposalKey) play();
  }, [proposalKey, play, stop]);
  return { animating, play, stop };
}
