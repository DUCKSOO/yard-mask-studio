import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  type ReactNode,
} from "react";

const HISTORY_MAX = 20;

export type AnnotationState = {
  width: number;
  height: number;
  history: Uint8Array[];
  cursor: number;
};

type AnnState = AnnotationState | null;

type Action =
  | { type: "RESET"; width: number; height: number }
  | { type: "PUSH"; cells: Uint8Array }
  | { type: "UNDO" }
  | { type: "REDO" };

function reducer(s: AnnState, a: Action): AnnState {
  if (a.type === "RESET") {
    const cells = new Uint8Array(a.width * a.height);
    return { width: a.width, height: a.height, history: [cells], cursor: 0 };
  }
  if (!s) {
    return s;
  }
  if (a.type === "PUSH") {
    let h = s.history.slice(0, s.cursor + 1);
    h.push(new Uint8Array(a.cells));
    if (h.length > HISTORY_MAX) {
      h = h.slice(-HISTORY_MAX);
    }
    return { ...s, history: h, cursor: h.length - 1 };
  }
  if (a.type === "UNDO") {
    if (s.cursor <= 0) {
      return s;
    }
    return { ...s, cursor: s.cursor - 1 };
  }
  if (a.type === "REDO") {
    if (s.cursor >= s.history.length - 1) {
      return s;
    }
    return { ...s, cursor: s.cursor + 1 };
  }
  return s;
}

export type AnnotationContextValue = {
  state: AnnState;
  current: Uint8Array | null;
  canUndo: boolean;
  canRedo: boolean;
  reset: (width: number, height: number) => void;
  pushCells: (cells: Uint8Array) => void;
  undo: () => void;
  redo: () => void;
};

const AnnotationContext = createContext<AnnotationContextValue | null>(null);

export function AnnotationProvider({ children }: { children: ReactNode }) {
  const [s, dispatch] = useReducer(reducer, null);

  const current = s ? s.history[s.cursor] : null;
  const canUndo = s ? s.cursor > 0 : false;
  const canRedo = s ? s.cursor < s.history.length - 1 : false;

  const reset = useCallback((width: number, height: number) => {
    dispatch({ type: "RESET", width, height });
  }, []);

  const pushCells = useCallback((cells: Uint8Array) => {
    dispatch({ type: "PUSH", cells });
  }, []);

  const undo = useCallback(() => {
    dispatch({ type: "UNDO" });
  }, []);

  const redo = useCallback(() => {
    dispatch({ type: "REDO" });
  }, []);

  const value = useMemo(
    () => ({
      state: s,
      current,
      canUndo,
      canRedo,
      reset,
      pushCells,
      undo,
      redo,
    }),
    [s, current, canUndo, canRedo, reset, pushCells, undo, redo],
  );

  return <AnnotationContext.Provider value={value}>{children}</AnnotationContext.Provider>;
}

export function useAnnotation(): AnnotationContextValue {
  const v = useContext(AnnotationContext);
  if (!v) {
    throw new Error("useAnnotation must be used within AnnotationProvider");
  }
  return v;
}

/** 브러시 원형 스탬프 — image 좌표, 값 0|1|255 */
export function paintBrush(
  cells: Uint8Array,
  width: number,
  height: number,
  cx: number,
  cy: number,
  radius: number,
  classId: number,
): Uint8Array {
  const out = new Uint8Array(cells);
  const r2 = radius * radius;
  const x0 = Math.max(0, Math.floor(cx - radius - 1));
  const x1 = Math.min(width - 1, Math.ceil(cx + radius + 1));
  const y0 = Math.max(0, Math.floor(cy - radius - 1));
  const y1 = Math.min(height - 1, Math.ceil(cy + radius + 1));
  for (let y = y0; y <= y1; y++) {
    for (let x = x0; x <= x1; x++) {
      const dx = x - cx;
      const dy = y - cy;
      if (dx * dx + dy * dy <= r2) {
        out[y * width + x] = classId;
      }
    }
  }
  return out;
}

/** SAM 스텁: 양성 포인트 주변 디스크를 occupied(1)로 */
export function applyPositiveDiskMask(
  cells: Uint8Array,
  width: number,
  height: number,
  px: number,
  py: number,
): Uint8Array {
  const r = Math.max(12, Math.min(width, height) / 10);
  return paintBrush(cells, width, height, px, py, r, 1);
}
