import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import { boot, run } from "./helpers";

/** The MCP server, driven over stdio as an assistant would. */
function startServer(port: number) {
  const proc: ChildProcessWithoutNullStreams = spawn(process.execPath, [join(import.meta.dirname, "..", "..", "mcp", "guess-mcp.mjs")], {
    env: { ...process.env, GUESS_MCP_PORT: String(port) },
  });
  let buf = "";
  const waiting = new Map<number, (v: any) => void>();
  let stderr = "";
  proc.stderr.on("data", (d) => (stderr += d));
  proc.stdout.on("data", (d) => {
    buf += d;
    let i;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i);
      buf = buf.slice(i + 1);
      const m = JSON.parse(line);
      waiting.get(m.id)?.(m);
      waiting.delete(m.id);
    }
  });
  let id = 0;
  const rpc = (method: string, params: object = {}) => new Promise<any>((resolve) => {
    const n = ++id;
    waiting.set(n, resolve);
    proc.stdin.write(JSON.stringify({ jsonrpc: "2.0", id: n, method, params }) + "\n");
  });
  return { proc, rpc, log: () => stderr };
}

test("an MCP client runs Gython in the page through the bridge", async ({ page }) => {
  const port = 17000 + Math.floor(Math.random() * 2000);
  const srv = startServer(port);
  try {
    await expect.poll(srv.log).toContain("waiting for a GUESS page");
    const init = await srv.rpc("initialize", { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "test", version: "1" } });
    expect(init.result.serverInfo.name).toBe("guess");
    const tools = await srv.rpc("tools/list");
    expect(tools.result.tools.map((t: any) => t.name)).toEqual(["run_gython", "get_graph_summary", "get_command_help", "get_screenshot"]);
    // no page yet: a clear message, not a crash
    const early = await srv.rpc("tools/call", { name: "run_gython", arguments: { code: "1 + 1" } });
    expect(early.result.isError).toBe(true);
    expect(early.result.content[0].text).toContain("connectAssistant()");

    await boot(page);
    await run(page, `connectAssistant(${port})`);
    await expect(page.locator("#assistant-status")).toHaveText("● assistant");

    const r = await srv.rpc("tools/call", { name: "run_gython", arguments: { code: "v1.color = red\nlen(g.nodes)" } });
    expect(r.result.isError).toBe(false);
    expect(r.result.content[0].text).toContain("402");
    await expect(page.locator(".cell[data-badge=assistant]").last()).toContainText("v1.color = red");
    const bad = await srv.rpc("tools/call", { name: "run_gython", arguments: { code: "colorize(nosuch)" } });
    expect(bad.result.isError).toBe(true);
    expect(bad.result.content[0].text).toMatch(/nosuch/);

    const sum = await srv.rpc("tools/call", { name: "get_graph_summary" });
    expect(sum.result.content[0].text).toContain("402 nodes");
    expect(sum.result.content[0].text).toContain("dept");
    const help = await srv.rpc("tools/call", { name: "get_command_help", arguments: { name: "colorize" } });
    expect(help.result.content[0].text).toMatch(/^colorize\(/);
    const shot = await srv.rpc("tools/call", { name: "get_screenshot" });
    expect(shot.result.content[0].type).toBe("image");
    expect(shot.result.content[0].data.length).toBeGreaterThan(1000);

    // the user can undo what the assistant did
    await run(page, "undo()\nundo()");
    await run(page, "v1.color");
    await expect(page.locator(".result").last()).not.toContainText("255,0,0");
    await run(page, "disconnectAssistant()");
    await expect(page.locator("#assistant-status")).toBeHidden();
  } finally {
    srv.proc.kill();
  }
});

test("the bridge refuses pages from other origins", async () => {
  const port = 19100 + Math.floor(Math.random() * 500);
  const srv = startServer(port);
  try {
    await expect.poll(srv.log).toContain("waiting for a GUESS page");
    const res = await new Promise<number>((resolve) => {
      const ws = new WebSocket(`ws://127.0.0.1:${port}`, { headers: { Origin: "https://evil.example" } } as any);
      ws.onopen = () => resolve(101);
      ws.onerror = () => resolve(403);
    });
    expect(res).toBe(403);
    await expect.poll(srv.log).toContain("refused a connection from origin");
  } finally {
    srv.proc.kill();
  }
});
