#!/usr/bin/env node
// GUESS for AI assistants: an MCP server (stdio) that runs Gython in an open
// GUESS page. Claude Desktop, Claude Code and other MCP clients start this
// script; the page connects to it with connectAssistant() (or File → Connect
// AI assistant), over a WebSocket on 127.0.0.1.
//
// Every command an assistant runs appears in the page's console as an
// ordinary cell marked "assistant": visible, undoable and in the history.
//
// No dependencies: Node 18+. Settings (environment variables):
//   GUESS_MCP_PORT     the WebSocket port (default 7777)
//   GUESS_ORIGINS      comma-separated page origins allowed to connect
//                      (default: GUESS on localhost ports 5173, 5318, 4173)
import { createHash } from "node:crypto";
import { createServer } from "node:http";
import { createInterface } from "node:readline";

const PORT = Number(process.env.GUESS_MCP_PORT || 7777);
const ORIGINS = new Set((process.env.GUESS_ORIGINS ||
  "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5318,http://127.0.0.1:5318,http://localhost:4173,http://127.0.0.1:4173")
  .split(",").map((s) => s.trim()).filter(Boolean));
const log = (...a) => process.stderr.write(`[guess-mcp] ${a.join(" ")}\n`);

// ---- the page, over a minimal WebSocket (RFC 6455: text frames, ping/close) ----
let page = null;                 // the connected socket
const waiting = new Map();       // request id -> {resolve, reject, timer}
let nextId = 1;

function frame(text, opcode = 0x1) {
  const data = Buffer.from(text);
  const n = data.length;
  const head = n < 126 ? Buffer.from([0x80 | opcode, n])
    : n < 65536 ? Buffer.from([0x80 | opcode, 126, n >> 8, n & 255])
    : Buffer.concat([Buffer.from([0x80 | opcode, 127]), (() => { const b = Buffer.alloc(8); b.writeBigUInt64BE(BigInt(n)); return b; })()]);
  return Buffer.concat([head, data]);
}

function attach(socket) {
  let buf = Buffer.alloc(0);
  let parts = [];
  socket.on("data", (chunk) => {
    buf = Buffer.concat([buf, chunk]);
    for (;;) {
      if (buf.length < 2) return;
      const fin = buf[0] & 0x80, op = buf[0] & 0x0f, masked = buf[1] & 0x80;
      let len = buf[1] & 0x7f, off = 2;
      if (len === 126) { if (buf.length < 4) return; len = buf.readUInt16BE(2); off = 4; }
      else if (len === 127) { if (buf.length < 10) return; len = Number(buf.readBigUInt64BE(2)); off = 10; }
      const need = off + (masked ? 4 : 0) + len;
      if (buf.length < need) return;
      let payload = buf.subarray(off + (masked ? 4 : 0), need);
      if (masked) {
        const mask = buf.subarray(off, off + 4);
        payload = Buffer.from(payload.map((b, i) => b ^ mask[i & 3]));
      }
      buf = buf.subarray(need);
      if (op === 0x8) { socket.end(frame("", 0x8)); return; }
      if (op === 0x9) { socket.write(frame(payload.toString(), 0xA)); continue; }
      if (op === 0x1 || op === 0x0) {
        parts.push(payload);
        if (fin) { onPage(Buffer.concat(parts).toString()); parts = []; }
      }
    }
  });
  const gone = () => {
    if (page === socket) {
      page = null;
      log("page disconnected");
      for (const [, w] of waiting) w.reject(new Error("the GUESS page disconnected"));
      waiting.clear();
    }
  };
  socket.on("close", gone);
  socket.on("error", gone);
}

function onPage(text) {
  let m;
  try { m = JSON.parse(text); } catch { return; }
  const w = waiting.get(m.id);
  if (!w) return;
  waiting.delete(m.id);
  clearTimeout(w.timer);
  if (m.error) w.reject(new Error(m.error)); else w.resolve(m.result);
}

function ask(method, params, ms = 120000) {
  if (!page) {
    return Promise.reject(new Error(
      "No GUESS page is connected. Open GUESS in a browser and run connectAssistant() in its console " +
      "(or File → Connect AI assistant)."));
  }
  const id = nextId++;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { waiting.delete(id); reject(new Error("GUESS did not answer in time")); }, ms);
    waiting.set(id, { resolve, reject, timer });
    page.write(frame(JSON.stringify({ id, method, params })));
  });
}

const http = createServer((_req, res) => { res.writeHead(426); res.end("GUESS MCP bridge: WebSocket only\n"); });
http.on("upgrade", (req, socket) => {
  const origin = req.headers.origin || "";
  if (!ORIGINS.has(origin)) {
    log(`refused a connection from origin ${JSON.stringify(origin)} (allow it with GUESS_ORIGINS)`);
    socket.end("HTTP/1.1 403 Forbidden\r\n\r\n");
    return;
  }
  const key = req.headers["sec-websocket-key"];
  if (!key) { socket.end("HTTP/1.1 400 Bad Request\r\n\r\n"); return; }
  const accept = createHash("sha1").update(key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest("base64");
  socket.write("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n" +
               `Sec-WebSocket-Accept: ${accept}\r\n\r\n`);
  if (page) page.end(frame("", 0x8));          // one page at a time: the newest wins
  page = socket;
  attach(socket);
  log(`page connected from ${origin}`);
});
http.on("error", (e) => log(`WebSocket server: ${e.message}`));
http.listen(PORT, "127.0.0.1", () => log(`waiting for a GUESS page on ws://127.0.0.1:${PORT}`));

// ---- MCP over stdio (JSON-RPC 2.0, one message per line) ----------------------
const TOOLS = [
  {
    name: "run_gython",
    description:
      "Run Gython (Python with graph shortcuts) in the open GUESS page, as a console cell the user sees and can undo. " +
      "Returns the printed output, the value of the last expression and any error. Examples: " +
      "\"colorize(dept)\", \"highest(betweenness, 5)\", \"(degree > 10).color = red\", \"louvainClusters()\". " +
      "Each run is one undo step; prefer several small runs over one long script.",
    inputSchema: { type: "object", properties: { code: { type: "string", description: "Gython source" } }, required: ["code"] },
  },
  {
    name: "get_graph_summary",
    description: "Size, density, components, degree statistics and the node and edge fields of the current graph (no changes).",
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "get_command_help",
    description: "Documentation for a GUESS command (e.g. \"colorize\"), or, without a name, the list of commands with one line each.",
    inputSchema: { type: "object", properties: { name: { type: "string" } } },
  },
  {
    name: "get_screenshot",
    description: "A PNG of the graph view as the user sees it now.",
    inputSchema: { type: "object", properties: {} },
  },
];

const INSTRUCTIONS =
  "GUESS is a graph exploration tool driven by Gython. Nodes are variables named after them (v1.color = red); " +
  "a comparison on a field selects (degree > 10); sets take field assignments ((dept == 'sales').size = 20). " +
  "Use get_graph_summary first, get_command_help for commands, run_gython to act, get_screenshot to look.";

function send(msg) { process.stdout.write(JSON.stringify(msg) + "\n"); }

async function callTool(name, args) {
  switch (name) {
    case "run_gython": {
      const r = await ask("run", { code: String(args?.code ?? "") });
      const text = (r.output || "").trim() || (r.ok ? "(no output)" : "(failed with no message)");
      return { content: [{ type: "text", text }], isError: !r.ok };
    }
    case "get_graph_summary": {
      const r = await ask("summary", {});
      return { content: [{ type: "text", text: r.text }] };
    }
    case "get_command_help": {
      const r = await ask("help", { name: args?.name ?? null });
      return { content: [{ type: "text", text: r.text }] };
    }
    case "get_screenshot": {
      const r = await ask("screenshot", {});
      const data = String(r.png).replace(/^data:image\/png;base64,/, "");
      return { content: [{ type: "image", data, mimeType: "image/png" }] };
    }
    default:
      throw Object.assign(new Error(`unknown tool ${name}`), { code: -32602 });
  }
}

async function onRequest(msg) {
  const { id, method, params } = msg;
  try {
    let result;
    if (method === "initialize") {
      result = {
        protocolVersion: params?.protocolVersion || "2025-06-18",
        capabilities: { tools: {} },
        serverInfo: { name: "guess", version: "1.0.0" },
        instructions: INSTRUCTIONS,
      };
    } else if (method === "ping") {
      result = {};
    } else if (method === "tools/list") {
      result = { tools: TOOLS };
    } else if (method === "tools/call") {
      try {
        result = await callTool(params?.name, params?.arguments ?? {});
      } catch (e) {
        if (e.code) throw e;
        result = { content: [{ type: "text", text: e.message }], isError: true };
      }
    } else {
      throw Object.assign(new Error(`method not found: ${method}`), { code: -32601 });
    }
    if (id !== undefined) send({ jsonrpc: "2.0", id, result });
  } catch (e) {
    if (id !== undefined) send({ jsonrpc: "2.0", id, error: { code: e.code || -32603, message: e.message } });
  }
}

createInterface({ input: process.stdin }).on("line", (line) => {
  if (!line.trim()) return;
  let msg;
  try { msg = JSON.parse(line); } catch { send({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "parse error" } }); return; }
  if (msg.method && msg.id === undefined) return;      // notifications (initialized, cancelled): nothing to do
  if (msg.method) void onRequest(msg);
}).on("close", () => process.exit(0));
