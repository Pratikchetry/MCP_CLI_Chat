# MCP CLI Chat

A terminal-based agentic AI system built on the **Model Context Protocol (MCP)** — the same architecture used by Claude Desktop, Cursor, and other production AI tooling. Nexus connects a free Groq LLM to a custom MCP document server, enabling multi-step reasoning, tool execution, and document management entirely from the command line.

---

## Architecture
```
┌─────────────────────────────────────────┐
│              CLI (main.py)              │
│         prompt-toolkit interface        │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│           CliChat / Chat                │
│   orchestrates messages & tool loops   │
└──────┬─────────────────────┬───────────┘
       │                     │
┌──────▼──────┐     ┌────────▼────────┐
│  core/      │     │   MCPClient     │
│  claude.py  │     │  (mcp_client.py)│
│  Groq LLM   │     │  stdio transport│
└─────────────┘     └────────┬────────┘
                             │ subprocess
                    ┌────────▼────────┐
                    │   mcp_server.py │
                    │  Tools          │
                    │  Resources      │
                    │  Prompts        │
                    └─────────────────┘
```

The MCP server runs as a child process of the main application, communicating over stdio — exactly how MCP works in production. The client and server share no memory; all communication happens over the MCP protocol.

---

## Features

### Agentic tool-use loop
The system runs a full agentic loop: the model receives tool schemas, decides which tools to call, the application executes them via the MCP client, results are fed back, and the loop continues until the model has enough information to respond — all transparently within a single user query.

### Document mentions via `@`
Inject document contents directly into context before the model is called:
```
> What are the key findings in @deposition.md?
```
No tool call needed — the content is embedded in the prompt automatically.

### Slash commands via `/`
Trigger server-side prompt templates with tab autocomplete:
```
> /summarize report.pdf
> /format plan.md
```
Prompts are defined, tested, and maintained on the server — clients consume them without needing to know the prompt internals.

### MCP Server capabilities

| Type | Name | Description |
|------|------|-------------|
| Tool | `read_doc_contents` | Read a document by ID |
| Tool | `edit_document` | Find-and-replace within a document |
| Resource | `docs://documents` | List all document IDs |
| Resource | `docs://documents/{doc_id}` | Fetch a specific document |
| Prompt | `format` | Rewrite a document in Markdown |
| Prompt | `summarize` | Produce a concise document summary |

---

## How the Agentic Loop Works
```
User input
    │
    ▼
Build message list ──► Send to Groq
                            │
                    stop_reason == "tool_use"?
                       YES │           NO │
                           ▼             ▼
                    Execute tools    Return final
                    via MCPClient    text response
                           │
                           ▼
                    Append tool results
                    to message list
                           │
                           └──► Send to Groq again
```

---

## Tech Stack

| Component | Library |
|-----------|---------|
| LLM API | [Groq](https://console.groq.com) — free tier, Llama 3.3 70B |
| MCP framework | `mcp[cli]` Python SDK |
| Terminal UI | `prompt-toolkit` |
| Env management | `python-dotenv` |

---

## Prerequisites

- Python 3.10+
- A free [Groq API key](https://console.groq.com)

---

## Setup

### Step 1: Configure environment variables

Create a `.env` file in the project root:
```env
GROQ_API_KEY=""        # Your Groq API key
GROQ_MODEL="llama-3.3-70b-versatile"
USE_UV=0               # Set to 1 if using uv
```

### Step 2: Install dependencies

#### Option 1: With uv (recommended)

[uv](https://github.com/astral-sh/uv) is a fast Python package installer and resolver.
```bash
pip install uv

uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

uv pip install -e .
```

#### Option 2: Without uv
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install groq "mcp[cli]>=1.8.0" prompt-toolkit python-dotenv
```

### Step 3: Run
```bash
# With uv
uv run main.py

# Without uv
python main.py
```

---

## Usage

### Basic chat
```
> What is the boiling point of water?
```

### Reference a document with `@`
```
> Tell me about @deposition.md
> Compare @report.pdf and @outlook.pdf
```

### Run a command with `/`
```
> /summarize deposition.md
> /format plan.md
```
Press **Tab** after `/` to autocomplete available commands.

---

## Testing the MCP Server in Isolation

Install `uv` first (`pip install uv`), then:
```bash
mcp dev mcp_server.py
```

Opens a browser-based inspector at `http://127.0.0.1:6274` — test all tools, resources, and prompts without running the full application.

---

## Project Structure
```
├── main.py              # Entry point — wires everything together
├── mcp_server.py        # MCP server: tools, resources, prompts
├── mcp_client.py        # MCP client wrapper (stdio transport)
├── core/
│   ├── claude.py        # Groq LLM adapter (Anthropic-compatible interface)
│   ├── chat.py          # Base chat loop with agentic tool-use
│   ├── cli_chat.py      # CLI-specific chat: @mentions, /commands
│   ├── cli.py           # Terminal UI (prompt-toolkit)
│   └── tools.py         # Tool schema conversion & execution
├── .env                 # API keys (not committed)
└── pyproject.toml
```

---

## Development

### Adding documents

Edit the `docs` dictionary in `mcp_server.py`:
```python
docs = {
    "your-file.md": "Document content goes here.",
    ...
}
```

### Adding MCP tools, resources, or prompts

All MCP server features are defined in `mcp_server.py` using decorators:
```python
@mcp.tool(name="my_tool", description="...")
def my_tool(param: str = Field(description="...")):
    ...

@mcp.resource("docs://my-resource")
def my_resource() -> str:
    ...

@mcp.prompt(name="my_prompt", description="...")
def my_prompt(doc_id: str = Field(...)) -> list[base.Message]:
    ...
```

---

## Implementation Notes

**API adapter layer** — Originally designed for the Anthropic SDK. `core/claude.py` contains a full message-format adapter that converts Anthropic-style conversation history and tool schemas to the OpenAI-compatible format Groq expects. No other file required changes — the abstraction boundary held cleanly.

**stdio transport** — The MCP server communicates over standard input/output, not HTTP. This is the MCP stdio transport — the same mechanism used by Claude Desktop and other MCP hosts in production.

**In-memory document store** — Documents are held in memory and do not persist between sessions. Persistent storage via SQLite or the filesystem is the natural next step.

---

