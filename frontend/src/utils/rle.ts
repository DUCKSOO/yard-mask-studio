/** C-order value:run_len RLE — backend mask_service.encode_rle_vl / decode_rle_vl 와 동일. */

export function encodeRleVl(mask: Uint8Array, width: number, height: number): string {
  if (mask.length !== width * height) {
    throw new Error("mask length mismatch");
  }
  if (mask.length === 0) {
    return "0:0";
  }
  let v0 = mask[0];
  let c = 1;
  const parts: string[] = [];
  for (let i = 1; i < mask.length; i++) {
    const x = mask[i];
    if (x === v0) {
      c += 1;
    } else {
      parts.push(`${v0}:${c}`);
      v0 = x;
      c = 1;
    }
  }
  parts.push(`${v0}:${c}`);
  return parts.join(",");
}

export function decodeRleVl(counts: string, height: number, width: number): Uint8Array {
  const total = height * width;
  const flat: number[] = [];
  for (const seg of counts.split(",")) {
    const s = seg.trim();
    if (!s) continue;
    const [vs, ls] = s.split(":", 2);
    const v = Number(vs);
    const ln = Number(ls);
    for (let k = 0; k < ln; k++) flat.push(v);
  }
  if (flat.length !== total) {
    throw new Error(`RLE total ${flat.length} != ${total}`);
  }
  return Uint8Array.from(flat);
}
