import { useEffect, useRef, useState } from "react";
import { errorMessage } from "./api";

export type Resource<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
};
/** The key gates rendering immediately, before effect cleanup can run. */
export function useResource<T>(
  key: string | null,
  load: (signal: AbortSignal) => Promise<T>,
): Resource<T> {
  const loader = useRef(load);
  loader.current = load;
  const [state, setState] = useState<Resource<T> & { key: string | null }>({
    key: null,
    data: null,
    loading: false,
    error: null,
  });
  useEffect(() => {
    if (key === null) return;
    const controller = new AbortController();
    let active = true;
    setState({ key, data: null, loading: true, error: null });
    const load = async () => loader.current(controller.signal);
    load()
      .then((data) => {
        if (active && !controller.signal.aborted)
          setState({ key, data, loading: false, error: null });
      })
      .catch((error) => {
        if (active && !controller.signal.aborted)
          setState({
            key,
            data: null,
            loading: false,
            error: errorMessage(error),
          });
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [key]);
  return state.key === key
    ? state
    : { data: null, loading: key !== null, error: null };
}
