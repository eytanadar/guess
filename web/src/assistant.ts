// connectAssistant(): the page side of the MCP bridge (mcp/guess-mcp.mjs).
// An AI assistant's tool calls arrive over a WebSocket on 127.0.0.1 and run
// here as ordinary console cells, marked "assistant", so the user sees and can
// undo everything it does.

export interface AssistantHost {
  run(code: string): Promise<{ ok: boolean; output: string }>;
  summary(): Promise<string>;
  help(name: string | null): Promise<string>;
  screenshot(): Promise<string>;
  status(text: string | null): void;
  note(text: string): void;
}

export class AssistantLink {
  private ws: WebSocket | null = null;
  private wanted = false;

  constructor(private host: AssistantHost) {}

  connect(url: string) {
    this.disconnect();
    this.wanted = true;
    const ws = new WebSocket(url);
    this.ws = ws;
    this.host.status("assistant: connecting…");
    ws.onopen = () => {
      this.host.status("● assistant");
      this.host.note(`Connected to the AI assistant bridge at ${url}. Commands it runs appear here marked "assistant"; ` +
        "undo works as usual. disconnectAssistant() ends it.");
    };
    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.ws = null;
      this.host.status(null);
      if (this.wanted) this.host.note("The AI assistant bridge closed. Start it from your assistant (mcp/guess-mcp.mjs) and run connectAssistant() again.");
      this.wanted = false;
    };
    ws.onmessage = (ev) => void this.onRequest(ws, String(ev.data));
  }

  disconnect() {
    this.wanted = false;
    this.ws?.close();
    this.ws = null;
    this.host.status(null);
  }

  get connected() {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  private async onRequest(ws: WebSocket, text: string) {
    let m: { id: number; method: string; params?: any };
    try {
      m = JSON.parse(text);
    } catch {
      return;
    }
    const reply = (body: object) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ id: m.id, ...body }));
    };
    try {
      switch (m.method) {
        case "run":
          reply({ result: await this.host.run(String(m.params?.code ?? "")) });
          break;
        case "summary":
          reply({ result: { text: await this.host.summary() } });
          break;
        case "help":
          reply({ result: { text: await this.host.help(m.params?.name ?? null) } });
          break;
        case "screenshot":
          reply({ result: { png: await this.host.screenshot() } });
          break;
        default:
          reply({ error: `unknown request ${m.method}` });
      }
    } catch (e) {
      reply({ error: String((e as Error)?.message ?? e) });
    }
  }
}
