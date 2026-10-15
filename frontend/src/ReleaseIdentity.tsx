import { request } from "./api";
import { useResource } from "./useResource";

type Identity = {
  name: string;
  version: string;
  revision: string | null;
  environment: "hosted" | "local";
};

export function ReleaseIdentity() {
  const result = useResource("release-identity", async (signal) => {
    const data = await request<Identity>("/release", undefined, signal);
    if (
      data.name !== "GreenHome Advisor" ||
      typeof data.version !== "string" ||
      !/^\d{4}\.\d{2}$/.test(data.version) ||
      !["hosted", "local"].includes(data.environment) ||
      (data.revision !== null &&
        (typeof data.revision !== "string" ||
          !/^[0-9a-f]{40}$/.test(data.revision)))
    ) {
      throw new Error("Invalid release metadata");
    }
    return data;
  });
  return (
    <section className="release-identity" aria-label="Release identity">
      <strong>Release identity</strong>
      {result.data ? (
        <p>
          GreenHome Advisor {result.data.version} ·{" "}
          {result.data.environment === "hosted"
            ? "Hosted runtime"
            : "Local runtime"}{" "}
          ·{" "}
          {result.data.revision
            ? `Revision ${result.data.revision.slice(0, 8)}`
            : "Revision not supplied"}
        </p>
      ) : (
        <p>
          {result.loading
            ? "Checking the running version…"
            : "Release metadata unavailable. No deployment revision is claimed."}
        </p>
      )}
    </section>
  );
}
