import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { getConfig, type LabelingConfig } from "../api/client";

export type ConfigContextValue = {
  config: LabelingConfig | null;
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
};

const ConfigContext = createContext<ConfigContextValue | null>(null);

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<LabelingConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const c = await getConfig();
      setConfig(c);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const value: ConfigContextValue = { config, loading, error, reload };
  return <ConfigContext.Provider value={value}>{children}</ConfigContext.Provider>;
}

export function useConfig(): ConfigContextValue {
  const v = useContext(ConfigContext);
  if (!v) {
    throw new Error("useConfig must be used within ConfigProvider");
  }
  return v;
}
