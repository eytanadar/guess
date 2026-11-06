// PDF, PostScript/EPS and GIF export of the current view (exportPDF, exportPS,
// exportEPS, exportGIF from the 2006 manual). Each wraps an image of the view;
// exportSVG remains the vector format. No dependencies.

/** Pixels of an image URL (PNG/JPEG data URL). */
async function pixels(url: string): Promise<ImageData> {
  const img = new Image();
  img.src = url;
  await img.decode();
  const c = document.createElement("canvas");
  c.width = img.naturalWidth;
  c.height = img.naturalHeight;
  const ctx = c.getContext("2d")!;
  ctx.drawImage(img, 0, 0);
  return ctx.getImageData(0, 0, c.width, c.height);
}

function bytes(s: string): Uint8Array<ArrayBuffer> {
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i) & 255;
  return out;
}

function concat(parts: Uint8Array[]): Uint8Array<ArrayBuffer> {
  const n = parts.reduce((a, p) => a + p.length, 0);
  const out = new Uint8Array(n);
  let k = 0;
  for (const p of parts) {
    out.set(p, k);
    k += p.length;
  }
  return out;
}

/** A one-page PDF holding a JPEG of the view, at 72 dpi (one point per pixel). */
export async function toPDF(jpegDataUrl: string): Promise<Blob> {
  const img = await pixels(jpegDataUrl);
  const w = img.width, h = img.height;
  const jpeg = Uint8Array.from(atob(jpegDataUrl.split(",")[1]), (c) => c.charCodeAt(0));
  const content = `q ${w} 0 0 ${h} 0 0 cm /Im0 Do Q`;
  const objs: Uint8Array[] = [
    bytes("<< /Type /Catalog /Pages 2 0 R >>"),
    bytes("<< /Type /Pages /Kids [3 0 R] /Count 1 >>"),
    bytes(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${w} ${h}] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>`),
    concat([bytes(`<< /Type /XObject /Subtype /Image /Width ${w} /Height ${h} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpeg.length} >>\nstream\n`), jpeg, bytes("\nendstream")]),
    bytes(`<< /Length ${content.length} >>\nstream\n${content}\nendstream`),
  ];
  const parts: Uint8Array[] = [bytes("%PDF-1.4\n%\xE2\xE3\xCF\xD3\n")];
  const offsets: number[] = [];
  let pos = parts[0].length;
  objs.forEach((o, i) => {
    offsets.push(pos);
    const p = concat([bytes(`${i + 1} 0 obj\n`), o, bytes("\nendobj\n")]);
    parts.push(p);
    pos += p.length;
  });
  const xref = `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n` + offsets.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("");
  parts.push(bytes(`${xref}trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${pos}\n%%EOF\n`));
  return new Blob([concat(parts) as Uint8Array<ArrayBuffer>], { type: "application/pdf" });
}

/** PostScript (or EPS with a bounding box) drawing the view with colorimage. */
export async function toPS(pngDataUrl: string, eps: boolean): Promise<Blob> {
  const img = await pixels(pngDataUrl);
  const { width: w, height: h, data } = img;
  const hex = "0123456789abcdef";
  const lines: string[] = [];
  let line = "";
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4;
      for (let c = 0; c < 3; c++) line += hex[data[i + c] >> 4] + hex[data[i + c] & 15];
      if (line.length >= 72) {
        lines.push(line);
        line = "";
      }
    }
  }
  if (line) lines.push(line);
  const head = eps
    ? `%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 ${w} ${h}\n%%Creator: GUESS\n%%EndComments\n`
    : `%!PS-Adobe-3.0\n%%Creator: GUESS\n%%Pages: 1\n%%EndComments\n%%Page: 1 1\n`;
  const body = `gsave\n/line ${w * 3} string def\n${w} ${h} scale\n${w} ${h} 8 [${w} 0 0 -${h} 0 ${h}]\n{currentfile line readhexstring pop} false 3 colorimage\n`;
  return new Blob([head, body, lines.join("\n"), "\ngrestore\nshowpage\n%%EOF\n"], { type: "application/postscript" });
}

/** A GIF of the view: 6x6x6 colour cube plus greys (no dithering), LZW-compressed. */
export async function toGIF(pngDataUrl: string): Promise<Blob> {
  const { width: w, height: h, data } = await pixels(pngDataUrl);
  // palette: 216-colour cube + 40 greys
  const pal = new Uint8Array(256 * 3);
  let k = 0;
  for (let r = 0; r < 6; r++) for (let g = 0; g < 6; g++) for (let b = 0; b < 6; b++) {
    pal[k++] = r * 51; pal[k++] = g * 51; pal[k++] = b * 51;
  }
  for (let i = 0; i < 40; i++) {
    const v = Math.round((i + 1) * 255 / 41);
    pal[k++] = v; pal[k++] = v; pal[k++] = v;
  }
  const idx = new Uint8Array(w * h);
  for (let p = 0; p < w * h; p++) {
    const r = data[p * 4], g = data[p * 4 + 1], b = data[p * 4 + 2];
    const cube = Math.round(r / 51) * 36 + Math.round(g / 51) * 6 + Math.round(b / 51);
    let best = cube;
    if (Math.abs(r - g) < 12 && Math.abs(g - b) < 12) {
      // near-grey: pick the closest of the cube colour and the grey ramp
      const grey = Math.min(39, Math.max(0, Math.round(((r + g + b) / 3) * 41 / 255) - 1));
      const dc = (pal[cube * 3] - r) ** 2 + (pal[cube * 3 + 1] - g) ** 2 + (pal[cube * 3 + 2] - b) ** 2;
      const gi = 216 + grey;
      const dg = (pal[gi * 3] - r) ** 2 + (pal[gi * 3 + 1] - g) ** 2 + (pal[gi * 3 + 2] - b) ** 2;
      if (dg < dc) best = gi;
    }
    idx[p] = best;
  }
  const lzw = lzwEncode(idx, 8);
  const out: number[] = [];
  const push16 = (v: number) => out.push(v & 255, (v >> 8) & 255);
  out.push(...bytes("GIF89a"));
  push16(w); push16(h);
  out.push(0xf7, 0, 0);                         // global colour table, 256 entries
  for (const v of pal) out.push(v);
  out.push(0x2c); push16(0); push16(0); push16(w); push16(h); out.push(0);
  out.push(8);                                  // LZW minimum code size
  for (let i = 0; i < lzw.length; i += 255) {
    const n = Math.min(255, lzw.length - i);
    out.push(n);
    for (let j = 0; j < n; j++) out.push(lzw[i + j]);
  }
  out.push(0, 0x3b);
  return new Blob([new Uint8Array(out)], { type: "image/gif" });
}

/** GIF-flavoured LZW (variable code width, clear code when the table fills). */
function lzwEncode(pixelsIdx: Uint8Array, minSize: number): Uint8Array {
  const clear = 1 << minSize, end = clear + 1;
  const out: number[] = [];
  let bitBuf = 0, bitCount = 0;
  let size = minSize + 1;
  const emit = (code: number) => {
    bitBuf |= code << bitCount;
    bitCount += size;
    while (bitCount >= 8) {
      out.push(bitBuf & 255);
      bitBuf >>>= 8;
      bitCount -= 8;
    }
  };
  let dict = new Map<number, number>();
  let next = end + 1;
  emit(clear);
  let prefix = pixelsIdx[0];
  for (let i = 1; i < pixelsIdx.length; i++) {
    const c = pixelsIdx[i];
    const key = prefix * 256 + c;
    const found = dict.get(key);
    if (found !== undefined) {
      prefix = found;
      continue;
    }
    emit(prefix);
    if (next < 4096) {
      dict.set(key, next++);
      if (next > (1 << size) && size < 12) size++;
    } else {
      emit(clear);
      dict = new Map();
      next = end + 1;
      size = minSize + 1;
    }
    prefix = c;
  }
  emit(prefix);
  emit(end);
  if (bitCount > 0) out.push(bitBuf & 255);
  return new Uint8Array(out);
}
