import { expect, test } from "@playwright/test";
import { copyFileSync, readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { boot, run } from "./helpers";

/** The stored entries of a zip: name and content. */
function entries(zip: Buffer): [string, Buffer][] {
  const out: [string, Buffer][] = [];
  let i = 0;
  while (zip.readUInt32LE(i) === 0x04034b50) {
    const size = zip.readUInt32LE(i + 18), nlen = zip.readUInt16LE(i + 26), xlen = zip.readUInt16LE(i + 28);
    const name = zip.subarray(i + 30, i + 30 + nlen).toString("utf8");
    const start = i + 30 + nlen + xlen;
    out.push([name, zip.subarray(start, start + size)]);
    i = start + size;
  }
  return out;
}

test("a loop's exports show each step and download as one zip", async ({ page }) => {
  await boot(page);
  const downloads: string[] = [];
  page.on("download", (d) => downloads.push(d.suggestedFilename()));
  const dl = page.waitForEvent("download");
  await run(page, [
    "startImages('frames.zip')",
    "for i, c in enumerate([red, blue, green]):",
    "    g.nodes.color = c",
    "    center(v1)",                      // a camera move: the export waits for it
    "    exportPNG('frame.png')",
    "exportSVG('graph.svg')",
    "stopImages()",
  ].join("\n"));
  await expect(page.locator(".cell").last()).not.toHaveClass(/failed/);
  const path = (await (await dl).path())!;
  if (process.env.ZIP_OUT) copyFileSync(path, process.env.ZIP_OUT);
  const zip = readFileSync(path);
  const files = entries(zip);
  expect(files.map(([n]) => n)).toEqual(["frame.png", "frame-2.png", "frame-3.png", "graph.svg"]);
  expect(files[0][1].subarray(1, 4).toString()).toBe("PNG");
  // three different pictures: each shows its own step
  const hashes = new Set(files.slice(0, 3).map(([, b]) => createHash("sha1").update(b).digest("hex")));
  expect(hashes.size).toBe(3);
  expect(files[3][1].toString()).toContain("<svg");
  await page.waitForTimeout(300);
  expect(downloads).toEqual(["frames.zip"]);     // one download, not four
  await expect(page.locator("#status")).toContainText("Saved 4 images in frames.zip");
});
