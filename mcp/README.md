# GUESS for AI assistants (MCP)

`guess-mcp.mjs` lets an AI assistant that speaks the Model Context Protocol
(Claude Desktop, Claude Code and others) work in an open GUESS page. It needs
Node 18 or later and nothing else.

**Set it up.** Add the bridge to your assistant:

- Claude Code: `claude mcp add guess -- node /path/to/guess/mcp/guess-mcp.mjs`
- Claude Desktop (`claude_desktop_config.json`):

  ```json
  {"mcpServers": {"guess": {"command": "node", "args": ["/path/to/guess/mcp/guess-mcp.mjs"]}}}
  ```

Then, in GUESS, choose *File → Connect AI assistant* or run
`connectAssistant()`. *● assistant* appears in the toolbar.

**Tools the assistant gets.**

| tool | does |
|---|---|
| `run_gython` | runs code as a console cell marked "assistant" (visible, undoable) and returns its output |
| `get_graph_summary` | size, components, degrees and fields, without changing anything |
| `get_command_help` | a command's documentation, or the list of commands |
| `get_screenshot` | a PNG of the graph view |

**Safety.**

- The bridge listens on 127.0.0.1 only.
- It accepts WebSocket connections only from GUESS pages: localhost ports 5173, 5318 and 4173 by default.
- For a GUESS you host, set `GUESS_ORIGINS=https://guess.example.org` (comma-separated for several).
- `GUESS_MCP_PORT` changes the port (default 7777); pass the same number to `connectAssistant(port)`.
- What the tools return (output, summaries, screenshots) goes to the assistant's service.
