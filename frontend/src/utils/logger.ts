const isDev =
  import.meta.env.VITE_APP_ENV === "dev" || import.meta.env.MODE === "development";

export const logger = {
  debug: (...args: unknown[]) => {
    if (isDev) {
      console.debug("[debug]", ...args);
    }
  },
  info: (...args: unknown[]) => {
    if (isDev) {
      console.info("[info]", ...args);
    }
  },
  warn: (...args: unknown[]) => {
    console.warn("[warn]", ...args);
  },
  error: (...args: unknown[]) => {
    console.error("[error]", ...args);
  },
};
