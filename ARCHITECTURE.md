# Ratatoskr MCP Server - Architecture & Call Flow

## Overview

The server uses a layered architecture with providers, managers, and MCP handlers.

## Component Hierarchy

```
MCP Server (server.py)
├── Resource Management Layer
│   ├── ResourceManager (maps URIs to providers)
│   ├── ResourceProvider (abstract base class)
│   │   ├── GnomeDesktopProvider (GNOME info)
│   │   └── DistroInfoProvider (OS info)
│   └── ResourceSerializer (converts data to JSON)
└── D-Bus Provider Layer
    └── GnomeShellProvider (queries D-Bus)
```

## Tool Call Flow

### When LLM asks: "What distribution am I running?"

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. LLM (Claude) via Hugin                                       │
│    Decides to call tool: get_distro_info                        │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. MCP Protocol (stdio)                                         │
│    Tool call request sent over stdin                            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. @server.call_tool() decorator (line 232)                     │
│    Intercepts tool call and routes to handle_call_tool()        │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. handle_call_tool(name="get_distro_info", arguments=None)     │
│    (line 233-274)                                               │
│    Checks: if name == "get_distro_info"                         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. resource_manager.get_resource("ratatoskr://distro/osinfo")   │
│    (line 257)                                                   │
│    ResourceManager looks up URI in self._providers dict         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. provider = self._providers["ratatoskr://distro/osinfo"]      │
│    (line 136)                                                   │
│    Returns: DistroInfoProvider instance                         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 7. await provider.get_resource()                                │
│    (line 143)                                                   │
│    Calls DistroInfoProvider.get_resource()                      │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 8. DistroInfoProvider.get_resource() (line 93)                  │
│    Opens /etc/os-release and parses it                          │
│    Returns: ResourceData(content={...})                         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 9. Check if resource_data.is_error (line 259)                   │
│    If error: return error message                               │
│    If success: continue                                         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 10. serializer.to_json(resource_data) (line 270)                │
│     Converts ResourceData.content dict to JSON string           │
│     Returns: '{"name": "Fedora", "version": "42", ...}'         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 11. Return [types.TextContent(type="text", text=json_string)]   │
│     (line 267-271)                                              │
│     Wraps JSON in MCP TextContent type                          │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 12. MCP Protocol (stdio)                                        │
│     Tool result sent back over stdout                           │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 13. Hugin receives result                                       │
│     Forwards to LLM (Claude)                                    │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 14. LLM (Claude)                                                │
│     Formats response: "You're running Fedora 42"                │
└─────────────────────────────────────────────────────────────────┘
```

## Parallel Flow: get_desktop_info (with D-Bus)

When LLM asks: "What version of GNOME am I running?"

```
handle_call_tool(name="get_desktop_info")
    │
    ├─> resource_manager.get_resource("ratatoskr://gnome/desktop")
    │       │
    │       └─> GnomeDesktopProvider.get_resource()
    │               │
    │               ├─> os.environ.get('DESKTOP_SESSION')  [environment vars]
    │               │
    │               └─> GnomeShellProvider()  [D-Bus provider]
    │                       │
    │                       └─> shell_provider.get_all_info()
    │                               │
    │                               └─> D-Bus queries via dbus_providers/gnome_shell.py
    │                                       │
    │                                       └─> Returns: {'version': '48.4', 'mode': 'user', ...}
    │
    └─> Returns ResourceData with combined info
            │
            └─> Serialized to JSON and sent back to LLM
```

## Key Classes & Their Roles

### ResourceData (line 22)
```python
@dataclass
class ResourceData:
    content: Dict[str, Any]  # The actual data
    mime_type: str           # "application/json"
    error: Optional[str]     # Error message if failed
```
**Purpose:** Container for data returned by providers

---

### ResourceProvider (line 35)
```python
class ResourceProvider(ABC):
    @abstractmethod
    async def get_resource(self) -> ResourceData:
        pass
```
**Purpose:** Base class that all data providers inherit from

---

### GnomeDesktopProvider (line 44)
```python
class GnomeDesktopProvider(ResourceProvider):
    async def get_resource(self) -> ResourceData:
        # Gets GNOME info via D-Bus
        # Returns desktop_environment, gnome_shell_version, etc.
```
**Purpose:** Fetches GNOME-specific information

---

### DistroInfoProvider (line 90)
```python
class DistroInfoProvider(ResourceProvider):
    async def get_resource(self) -> ResourceData:
        # Reads /etc/os-release
        # Returns name, version, id, etc.
```
**Purpose:** Fetches distribution information

---

### ResourceManager (line 125)
```python
class ResourceManager:
    def __init__(self):
        self._providers = {
            "ratatoskr://gnome/desktop": GnomeDesktopProvider(),
            "ratatoskr://distro/osinfo": DistroInfoProvider(),
        }

    async def get_resource(self, uri: str) -> ResourceData:
        provider = self._providers.get(uri)
        return await provider.get_resource()
```
**Purpose:** Maps URIs to providers (like a router)

---

### ResourceSerializer (line 150)
```python
class ResourceSerializer:
    @staticmethod
    def to_json(resource_data: ResourceData) -> str:
        return json.dumps(resource_data.content, indent=2)
```
**Purpose:** Converts ResourceData to JSON strings

---

## MCP Handlers (Decorated Functions)

### @server.list_tools() (line 207)
```python
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(name="get_desktop_info", ...),
        types.Tool(name="get_distro_info", ...),
    ]
```
**When called:** When Hugin starts and queries available tools
**Purpose:** Tells LLM what tools are available

---

### @server.call_tool() (line 232)
```python
async def handle_call_tool(name: str, arguments: dict | None):
    if name == "get_desktop_info":
        # Call GnomeDesktopProvider
    elif name == "get_distro_info":
        # Call DistroInfoProvider
```
**When called:** When LLM decides to use a tool
**Purpose:** Execute the requested tool and return results

---

### @server.list_resources() (line 177)
```python
async def handle_list_resources() -> list[types.Resource]:
    return [
        types.Resource(uri="ratatoskr://gnome/desktop", ...),
        types.Resource(uri="ratatoskr://distro/osinfo", ...),
    ]
```
**When called:** When Hugin queries available resources (not commonly used)
**Purpose:** List URIs that can be read (alternative to tools)

---

### @server.read_resource() (line 196)
```python
async def handle_read_resource(uri: types.AnyUrl) -> str:
    resource_data = await resource_manager.get_resource(str(uri))
    return serializer.to_json(resource_data)
```
**When called:** When a resource is read by URI (not commonly used)
**Purpose:** Direct resource access (alternative to tools)

---

## Data Flow Summary

```
Tool Request → handle_call_tool()
                    ↓
              resource_manager.get_resource(uri)
                    ↓
              Looks up provider by URI
                    ↓
              provider.get_resource()
                    ↓
              Returns ResourceData
                    ↓
              serializer.to_json()
                    ↓
              Returns JSON string
                    ↓
              Wrapped in TextContent
                    ↓
              Sent back via MCP
```

## Why This Architecture?

1. **Separation of Concerns:**
   - Providers handle data fetching
   - Manager handles routing
   - Serializer handles formatting
   - MCP handlers handle protocol

2. **Extensibility:**
   - Add new provider → inherit from ResourceProvider
   - Register in ResourceManager
   - Add tool in handle_list_tools()
   - Add case in handle_call_tool()

3. **Testability:**
   - Each provider can be tested independently
   - ResourceManager can be mocked
   - Clear boundaries between components

## Adding a New Tool - Step by Step

Want to add a tool to get CPU info? Here's how:

**Step 1:** Create provider
```python
class CpuInfoProvider(ResourceProvider):
    async def get_resource(self) -> ResourceData:
        # Read /proc/cpuinfo or use psutil
        return ResourceData(content={"cores": 8, "model": "..."})
```

**Step 2:** Register in ResourceManager (line 129)
```python
self._providers = {
    "ratatoskr://gnome/desktop": GnomeDesktopProvider(),
    "ratatoskr://distro/osinfo": DistroInfoProvider(),
    "ratatoskr://system/cpu": CpuInfoProvider(),  # <-- Add this
}
```

**Step 3:** Add tool definition (line 220)
```python
types.Tool(
    name="get_cpu_info",
    description="Get CPU information",
    inputSchema={"type": "object", "properties": {}, "required": []},
)
```

**Step 4:** Add handler case (line 273)
```python
elif name == "get_cpu_info":
    resource_data = await resource_manager.get_resource("ratatoskr://system/cpu")
    # ... same pattern as other tools
```

Done! The LLM can now call `get_cpu_info`.

---

## Email & Memory Systems (Evolution + Muninn)

### Email Architecture (EvolutionEmailManager)

**Evolution Choice:** Evolution stores emails in SQLite databases with built-in indexes, enabling instant queries across 190,000+ emails without sequential scanning.

**Architecture:**
```
EmailProvider (email.py)
    ↓
EvolutionEmailManager (utils/evolution_email.py)
    ↓
SQLite Databases (~/.var/app/org.gnome.Evolution/cache/evolution/mail/)
    ├── Account 1/folders.db
    ├── Account 2/folders.db
    └── Account 3/folders.db
        ├── folders table (folder_name, saved_count, unread_count)
        └── messages_N tables (uid, subject, mail_from, mail_to, dsent, size, flags)
```

**Database Schema:**
Evolution uses multiple `messages_N` tables (messages_1 through messages_28) in each account's `folders.db`. Key fields:
- `uid` - Unique message identifier
- `subject` - Email subject line
- `mail_from` - Sender email
- `mail_to` - Recipients
- `mail_cc` - CC recipients
- `dsent` - Send date (Unix timestamp, indexed!)
- `size` - Email size in bytes
- `flags` - Message flags

**Query Performance:**
```python
# Find emails from specific sender in last 2 weeks
SELECT * FROM messages_3
WHERE mail_from LIKE '%nikshi%'
  AND dsent >= 1730419200
ORDER BY dsent DESC
LIMIT 3;
```

**Performance Characteristics:**
- ✅ **First query**: ~350ms (includes connection overhead)
- ✅ **Subsequent queries**: ~20ms (instant!)
- ✅ **Search across 190,000+ emails**: No performance degradation
- ✅ **Date range filtering**: Instant via indexed `dsent` column
- ✅ **No timeouts**: SQLite queries complete in milliseconds

**Design Benefits:**
1. **No Sequential Scanning** - Indexed queries jump directly to relevant emails
2. **Multiple Account Support** - Each account has separate database
3. **Built-in Indexing** - Evolution maintains indexes automatically
4. **Concurrent Access** - Multiple queries can run without blocking

**Tools Provided:**
- `query_emails` - Fast search with filters (sender, recipient, subject, date)
- `get_email_accounts` - List configured Evolution accounts
- `get_email_folders` - List folders per account
- `get_email_content` - Fetch full email body (Note: requires mbox access for full content)
- `find_ical_emails` - Find meeting invitations

---

### Memory System (Muninn)

**Purpose:** Store conversational context about emails for semantic recall

**Architecture:**
```
EmailProvider ──┐
                ├──> MuninnProvider ──> ChromaDB (Vector Store)
UserQuery  ─────┘                       └─> Embeddings (MiniLM-L6-v2)
```

**Why ChromaDB?**
- Local-first (no cloud dependency)
- Built-in embedding generation
- Semantic search out-of-box
- Small footprint (~80MB model)

**Data Schema:**
```python
{
    'id': 'email_<msg-id>_<timestamp>',
    'email_message_id': '<original@msg.id>',
    'email_subject': 'Meeting about X',
    'email_sender': 'person@example.com',
    'email_date': '2025-08-29T12:00:00',
    'context': 'Full discussion summary...',  # Embedded for semantic search
    'tags': ['work', 'urgent', 'follow-up'],
    'notes': 'Additional notes...'
}
```

**Query Patterns:**

1. **Exact Recall** (by Message-ID)
   ```python
   muninn_recall(email_message_id="<123@gmail.com>")
   # → Returns all memories for this specific email
   ```

2. **Semantic Search** (by meaning)
   ```python
   muninn_search(query="discussions about the Filigran opportunity")
   # → Returns relevant memories ranked by similarity
   # Uses ChromaDB's cosine similarity on embeddings
   ```

3. **Filtered Search** (by tags/sender)
   ```python
   muninn_search(
       query="meeting preparations",
       tags=["work", "urgent"],
       sender="boss@company.com"
   )
   ```

**Performance:**
- Memory storage: <100ms (embedding + insert)
- Semantic search: <500ms (even with 1000s of memories)
- Storage: ~/.local/share/ratatoskr/muninn

**Tools Provided:**
- `muninn_remember` - Store context about email discussions
- `muninn_recall` - Retrieve by email Message-ID
- `muninn_search` - Semantic search across all memories
- `muninn_update` - Update existing memory
- `muninn_forget` - Delete memory
- `muninn_stats` - Get statistics

**Use Cases:**
1. "What did I discuss with John about the project?"
2. "Show me all work-related urgent follow-ups"
3. "What decisions were made in the Filigran emails?"
4. "Find discussions about meeting scheduling"

---

## Performance Best Practices

### Email Queries
1. ✅ **Always specify narrow time ranges** (days_back=30 or less)
2. ✅ **Use sender/recipient filters** to reduce result sets
3. ✅ **Query metadata first**, fetch content only if needed
4. ❌ **Avoid:** No filters on large mailboxes
5. ❌ **Avoid:** Searching all folders without limit

### Memory Usage
1. ✅ **Store summaries**, not full email content
2. ✅ **Use tags** for efficient categorical filtering
3. ✅ **Semantic search** for fuzzy/contextual queries
4. ✅ **Update memories** rather than duplicating
