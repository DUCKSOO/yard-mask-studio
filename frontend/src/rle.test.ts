import { describe, expect, it } from "vitest";
import { decodeRleVl, encodeRleVl } from "./utils/rle";

describe("rle", () => {
  it("roundtrips C-order mask", () => {
    const w = 4;
    const h = 3;
    const u = new Uint8Array(w * h);
    u.fill(0);
    u[5] = 1;
    u[6] = 255;
    const s = encodeRleVl(u, w, h);
    const back = decodeRleVl(s, h, w);
    expect([...back]).toEqual([...u]);
  });
});
