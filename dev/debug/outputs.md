```bash
gabri@Bladee:~/dev/stelae$ curl -s http://127.0.0.1:9092/.well-known/mcp/manifest.json | jq .
{
  "description": "Local MCP stack",
  "name": "Stelae MCP Proxy",
  "prompts": [
    {
      "name": "documentation_sources",
      "description": "List all available documentation sources with their URLs and types"
    },
    {
      "name": "documentation_page",
      "description": "Fetch the full content of a documentation page at a specific URL as markdown",
      "arguments": [
        {
          "name": "url",
          "required": true
        }
      ]
    },
    {
      "name": "documentation_links",
      "description": "Fetch all links from a documentation page to discover related content",
      "arguments": [
        {
          "name": "url",
          "required": true
        }
      ]
    },
    {
      "name": "Continue Conversation",
      "description": "Continue a previous conversation",
      "arguments": [
        {
          "name": "topic",
          "description": "Topic or keyword to search for\n\nProvide as a JSON string matching the following schema: {\"anyOf\":[{\"type\":\"string\"},{\"type\":\"null\"}],\"description\":\"Topic or keyword to search for\"}"
        },
        {
          "name": "timeframe",
          "description": "How far back to look for activity (e.g. '1d', '1 week')\n\nProvide as a JSON string matching the following schema: {\"anyOf\":[{\"type\":\"string\"},{\"type\":\"null\"}],\"description\":\"How far back to look for activity (e.g. '1d', '1 week')\"}"
        }
      ]
    },
    {
      "name": "Share Recent Activity",
      "description": "Get recent activity from across the knowledge base",
      "arguments": [
        {
          "name": "timeframe",
          "description": "How far back to look for activity (e.g. '1d', '1 week')\n\nProvide as a JSON string matching the following schema: {\"description\":\"How far back to look for activity (e.g. '1d', '1 week')\",\"type\":\"string\"}"
        }
      ]
    },
    {
      "name": "Search Knowledge Base",
      "description": "Search across all content in basic-memory",
      "arguments": [
        {
          "name": "query",
          "required": true
        },
        {
          "name": "timeframe",
          "description": "How far back to search (e.g. '1d', '1 week')\n\nProvide as a JSON string matching the following schema: {\"anyOf\":[{\"type\":\"string\"},{\"type\":\"null\"}],\"description\":\"How far back to search (e.g. '1d', '1 week')\"}"
        }
      ]
    },
    {
      "name": "fetch",
      "description": "Fetch a URL and extract its contents as markdown",
      "arguments": [
        {
          "name": "url",
          "description": "URL to fetch",
          "required": true
        }
      ]
    }
  ],
  "resources": [
    {
      "uri": "grep://info",
      "name": "grep_info",
      "description": "Resource providing information about the grep binary.",
      "mimeType": "text/plain"
    },
    {
      "uri": "documentation://sources",
      "name": "documentation://sources",
      "mimeType": "text/plain"
    },
    {
      "uri": "memory://ai_assistant_guide",
      "name": "ai assistant guide",
      "description": "Give an AI assistant guidance on how to use Basic Memory tools effectively",    
      "mimeType": "text/plain"
    },
    {
      "uri": "memory://project_info",
      "name": "project_info",
      "description": "Get information and statistics about the current Basic Memory project.",        
      "mimeType": "text/plain"
    }
  ],
  "servers": [
    {
      "name": "fs",
      "type": "sse",
      "url": "https://mcp.infotopology.xyz/fs/sse"
    },
    {
      "name": "rg",
      "type": "sse",
      "url": "https://mcp.infotopology.xyz/rg/sse"
    },
    {
      "name": "sh",
      "type": "sse",
      "url": "https://mcp.infotopology.xyz/sh/sse"
    },
    {
      "name": "docs",
      "type": "sse",
      "url": "https://mcp.infotopology.xyz/docs/sse"
    },
    {
      "name": "mem",
      "type": "sse",
      "url": "https://mcp.infotopology.xyz/mem/sse"
    },
    {
      "name": "fetch",
      "type": "sse",
      "url": "https://mcp.infotopology.xyz/fetch/sse"
    },
    {
      "name": "strata",
      "type": "sse",
      "url": "https://mcp.infotopology.xyz/strata/sse"
    }
  ],
  "tools": [
    {
      "annotations": {},
      "description": "Search for pattern in files using system grep.\n    \n    Args:\n        pattern: Pattern to search for\n        paths: File or directory paths to search in (string or list of strings)\n        ignore_case: Case-insensitive matching (-i)\n        before_context: Number of lines before match (-B)\n        after_context: Number of lines after match (-A)\n        context: Number of context lines around match (equal before/after)\n        max_count: Stop after N matches (-m)\n        fixed_strings: Treat pattern as literal text, not regex (-F)\n        recursive: Search directories recursively (-r)\n        regexp: Use regular expressions for pattern matching\n        invert_match: Select non-matching lines (-v)\n        line_number: Show line numbers (-n)\n        file_pattern: Pattern to filter files (e.g., \"*.txt\")\n        \n    Returns:\n        JSON string with search results\n    ",
      "inputSchema": {
        "type": "object",
        "properties": {
          "after_context": {
            "default": 0,
            "title": "After Context",
            "type": "integer"
          },
          "before_context": {
            "default": 0,
            "title": "Before Context",
            "type": "integer"
          },
          "context": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "Context"
          },
          "file_pattern": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "default": null,
            "title": "File Pattern"
          },
          "fixed_strings": {
            "default": false,
            "title": "Fixed Strings",
            "type": "boolean"
          },
          "ignore_case": {
            "default": false,
            "title": "Ignore Case",
            "type": "boolean"
          },
          "invert_match": {
            "default": false,
            "title": "Invert Match",
            "type": "boolean"
          },
          "line_number": {
            "default": true,
            "title": "Line Number",
            "type": "boolean"
          },
          "max_count": {
            "default": 0,
            "title": "Max Count",
            "type": "integer"
          },
          "paths": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              }
            ],
            "title": "Paths"
          },
          "pattern": {
            "title": "Pattern",
            "type": "string"
          },
          "recursive": {
            "default": false,
            "title": "Recursive",
            "type": "boolean"
          },
          "regexp": {
            "default": true,
            "title": "Regexp",
            "type": "boolean"
          }
        },
        "required": [
          "pattern",
          "paths"
        ]
      },
      "name": "grep",
      "outputSchema": {
        "type": "object",
        "properties": {
          "result": {
            "additionalProperties": true,
            "title": "Result",
            "type": "object"
          }
        },
        "required": [
          "result"
        ]
      }
    },
    {
      "annotations": {},
      "description": "\n    Execute terminal command and return results\n    \n    Args:\n        command: Command line command to execute\n        timeout: Command timeout in seconds, default is 30 seconds\n    \n    Returns:\n        Output of the command execution\n    ",
      "inputSchema": {
        "type": "object",
        "properties": {
          "command": {
            "title": "Command",
            "type": "string"
          },
...

# note: full thing is huge so I cut it off here, if you need more just ping me

---

gabri@Bladee:~/dev/stelae$ curl -s http://127.0.0.1:9092/ | head -n1
404 page not found

---

gabri@Bladee:~/dev/stelae$ curl -sI http://127.0.0.1:9092/mem/sse | sed -n '1,10p'
HTTP/1.1 405 Method Not Allowed
Content-Type: text/plain; charset=utf-8
X-Content-Type-Options: nosniff
Date: Fri, 26 Sep 2025 22:54:41 GMT
Content-Length: 19

---

gabri@Bladee:~/dev/stelae$ source ~/.nvm/nvm.sh && pm2 status
┌────┬────────────────────┬──────────┬──────┬───────────┬──────────┬──────────┐
│ id │ name               │ mode     │ ↺    │ status    │ cpu      │ memory   │
├────┼────────────────────┼──────────┼──────┼───────────┼──────────┼──────────┤
│ 6  │ 1mcp               │ fork     │ 0    │ online    │ 0%       │ 97.4mb   │
│ 3  │ docy               │ fork     │ 0    │ online    │ 0%       │ 117.0mb  │
│ 1  │ mcp-bridge         │ fork     │ 210  │ online    │ 0%       │ 54.2mb   │
│ 0  │ mcp-proxy          │ fork     │ 0    │ online    │ 0%       │ 9.8mb    │
│ 4  │ memory             │ fork     │ 0    │ online    │ 0%       │ 128.9mb  │
│ 5  │ shell              │ fork     │ 0    │ online    │ 0%       │ 54.2mb   │
│ 2  │ strata             │ fork     │ 0    │ online    │ 0%       │ 64.1mb   │
└────┴────────────────────┴──────────┴──────┴───────────┴──────────┴──────────┘

---

gabri@Bladee:~/dev/stelae$ source ~/.nvm/nvm.sh && pm2 logs mcp-proxy --lines 120
[TAILING] Tailing last 120 lines for [mcp-proxy] process (change the value with --lines option)
/home/gabri/dev/stelae/logs/mcp-proxy.out.log last 120 lines:
/home/gabri/dev/stelae/logs/mcp-proxy.err.log last 120 lines:
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Successfully listed 19 tools
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding tool delete_note
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding tool read_content
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding tool build_context
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding tool recent_activity
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding tool search_notes
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding tool read_note
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding tool view_note
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding tool write_note
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding tool canvas
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding tool list_directory
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding tool edit_note
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding tool move_note
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding tool sync_status
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding tool list_memory_projects
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding tool switch_project
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding tool get_current_project
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding tool set_default_project
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding tool create_memory_project
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding tool delete_project
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Successfully listed 3 prompts
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding prompt Continue Conversation       
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding prompt Share Recent Activity       
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding prompt Search Knowledge Base       
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Successfully listed 2 resources
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding resource ai assistant guide        
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Adding resource project_info
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Connected
0|mcp-prox | 2025-09-26T18:57:14: 2025/09/26 18:57:14 <mem> Handling requests at /mem/
0|mcp-prox | 2025-09-26T18:59:00: 2025/09/26 18:59:00 Shutdown signal received
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <sh> Connecting
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <docs> Connecting
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <mem> Connecting
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <fetch> Connecting
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <strata> Connecting
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <fs> Connecting
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <rg> Connecting
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 Starting sse server
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 sse server listening on :9092
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <rg> Successfully initialized MCP client        
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <rg> Successfully listed 1 tools
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <rg> Adding tool grep
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <rg> Successfully listed 1 resources
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <rg> Adding resource grep_info
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <rg> Connected
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <rg> Handling requests at /rg/
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <sh> Successfully initialized MCP client        
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <sh> Successfully listed 10 tools
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <sh> Adding tool execute_command
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <sh> Adding tool get_command_history
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <sh> Adding tool get_current_directory
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <sh> Adding tool change_directory
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <sh> Adding tool list_directory
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <sh> Adding tool write_file
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <sh> Adding tool read_file
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <sh> Adding tool insert_file_content
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <sh> Adding tool delete_file_content
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <sh> Adding tool update_file_content
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <sh> Connected
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <sh> Handling requests at /sh/
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <fetch> Successfully initialized MCP client     
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <fetch> Successfully listed 1 tools
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <fetch> Adding tool fetch
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <fetch> Successfully listed 1 prompts
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <fetch> Adding prompt fetch
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <fetch> Connected
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <fetch> Handling requests at /fetch/
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <strata> Successfully initialized MCP client    
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <strata> Successfully listed 5 tools
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <strata> Adding tool discover_server_actions    
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <strata> Adding tool get_action_details
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <strata> Adding tool execute_action
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <strata> Adding tool search_documentation       
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <strata> Adding tool handle_auth_failure        
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <strata> Connected
0|mcp-prox | 2025-09-26T18:59:03: 2025/09/26 18:59:03 <strata> Handling requests at /strata/
0|mcp-prox | 2025-09-26T18:59:04: 2025/09/26 18:59:04 <docs> Successfully initialized MCP client      
0|mcp-prox | 2025-09-26T18:59:04: 2025/09/26 18:59:04 <docs> Successfully listed 3 tools
0|mcp-prox | 2025-09-26T18:59:04: 2025/09/26 18:59:04 <docs> Adding tool list_documentation_sources_tool
0|mcp-prox | 2025-09-26T18:59:04: 2025/09/26 18:59:04 <docs> Adding tool fetch_documentation_page     
0|mcp-prox | 2025-09-26T18:59:04: 2025/09/26 18:59:04 <docs> Adding tool fetch_document_links
0|mcp-prox | 2025-09-26T18:59:04: 2025/09/26 18:59:04 <docs> Successfully listed 3 prompts
0|mcp-prox | 2025-09-26T18:59:04: 2025/09/26 18:59:04 <docs> Adding prompt documentation_sources      
0|mcp-prox | 2025-09-26T18:59:04: 2025/09/26 18:59:04 <docs> Adding prompt documentation_page
0|mcp-prox | 2025-09-26T18:59:04: 2025/09/26 18:59:04 <docs> Adding prompt documentation_links        
0|mcp-prox | 2025-09-26T18:59:04: 2025/09/26 18:59:04 <docs> Successfully listed 1 resources
0|mcp-prox | 2025-09-26T18:59:04: 2025/09/26 18:59:04 <docs> Adding resource documentation://sources  
0|mcp-prox | 2025-09-26T18:59:04: 2025/09/26 18:59:04 <docs> Connected
0|mcp-prox | 2025-09-26T18:59:04: 2025/09/26 18:59:04 <docs> Handling requests at /docs/
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Successfully initialized MCP client       
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Successfully listed 19 tools
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding tool delete_note
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding tool read_content
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding tool build_context
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding tool recent_activity
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding tool search_notes
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding tool read_note
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding tool view_note
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding tool write_note
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding tool canvas
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding tool list_directory
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding tool edit_note
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding tool move_note
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding tool sync_status
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding tool list_memory_projects
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding tool switch_project
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding tool get_current_project
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding tool set_default_project
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding tool create_memory_project
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding tool delete_project
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Successfully listed 3 prompts
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding prompt Continue Conversation       
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding prompt Share Recent Activity       
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding prompt Search Knowledge Base       
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Successfully listed 2 resources
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding resource ai assistant guide        
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Adding resource project_info
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Connected
0|mcp-prox | 2025-09-26T18:59:05: 2025/09/26 18:59:05 <mem> Handling requests at /mem/
0|mcp-prox | 2025-09-26T23:54:41: 2025/09/26 23:54:41 <mem> Request [HEAD] /mem/sse

---

gabri@Bladee:~/dev/stelae$ source ~/.nvm/nvm.sh && pm2 logs mcp-bridge --lines 60
[TAILING] Tailing last 60 lines for [mcp-bridge] process (change the value with --lines option)
/home/gabri/dev/stelae/logs/mcp-bridge.out.log last 60 lines:
1|mcp-brid | 2025-09-26T13:02:17: INFO:     92.20.131.75:0 - "GET /version HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T13:02:17: INFO:     92.20.131.75:0 - "HEAD /mcp HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T13:02:35: INFO:     92.20.131.75:0 - "POST /mcp HTTP/1.1" 503 Service Unavailable
1|mcp-brid | 2025-09-26T13:03:35: INFO:     92.20.131.75:0 - "HEAD /mcp HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T13:03:53: INFO:     92.20.131.75:0 - "POST /mcp HTTP/1.1" 503 Service Unavailable
1|mcp-brid | 2025-09-26T13:03:53: INFO:     92.20.131.75:0 - "GET /healthz HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T13:03:53: INFO:     92.20.131.75:0 - "GET /version HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T13:03:53: INFO:     92.20.131.75:0 - "GET /.well-known/mcp/manifest.json HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T13:34:36: INFO:     92.20.131.75:0 - "GET /mcp HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T13:34:48: INFO:     92.20.131.75:0 - "POST /mcp HTTP/1.1" 503 Service Unavailable
1|mcp-brid | 2025-09-26T13:36:17: INFO:     92.20.131.75:0 - "GET /mcp HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T13:36:22: INFO:     92.20.131.75:0 - "POST /mcp HTTP/1.1" 503 Service Unavailable
1|mcp-brid | 2025-09-26T13:37:00: INFO:     92.20.131.75:0 - "GET /mcp HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T13:37:26: INFO:     92.20.131.75:0 - "POST /mcp HTTP/1.1" 503 Service Unavailable
1|mcp-brid | 2025-09-26T13:38:05: INFO:     92.20.131.75:0 - "POST /mcp HTTP/1.1" 503 Service Unavailable
1|mcp-brid | 2025-09-26T13:46:59: INFO:     92.20.131.75:0 - "GET /mcp HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T13:47:15: INFO:     92.20.131.75:0 - "POST /mcp HTTP/1.1" 503 Service Unavailable
1|mcp-brid | 2025-09-26T14:04:10: INFO:     92.20.131.75:0 - "GET /version HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T14:04:10: INFO:     92.20.131.75:0 - "GET /mcp HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T14:04:10: [2025-09-26 14:04:10] [bridge] WARNING: No upstream SSE path confirmed; falling back to /stream
1|mcp-brid | 2025-09-26T14:04:10: [2025-09-26 14:04:10] [bridge:604ac049801c471b8370e116ed796b4d] Upstream SSE error: Client error '404 Not Found' for url 'http://127.0.0.1:9092/stream'
1|mcp-brid | 2025-09-26T14:04:10: For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404
1|mcp-brid | 2025-09-26T14:04:25: INFO:     92.20.131.75:0 - "POST /mcp HTTP/1.1" 503 Service Unavailable
1|mcp-brid | 2025-09-26T14:05:07: INFO:     127.0.0.1:34512 - "HEAD /mcp HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T14:05:07: INFO:     127.0.0.1:34526 - "GET /healthz HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T14:05:07: INFO:     127.0.0.1:34528 - "GET /version HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T14:05:14: INFO:     92.20.131.75:0 - "GET /version HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T14:05:14: INFO:     92.20.131.75:0 - "GET /mcp HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T14:05:14: [2025-09-26 14:05:14] [bridge] WARNING: No upstream SSE path confirmed; falling back to /stream
1|mcp-brid | 2025-09-26T14:05:15: [2025-09-26 14:05:15] [bridge:499e9537554d422da68fa0e469b93c02] Upstream SSE error: Client error '404 Not Found' for url 'http://127.0.0.1:9092/stream'
1|mcp-brid | 2025-09-26T14:05:15: For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404
1|mcp-brid | 2025-09-26T14:05:27: INFO:     92.20.131.75:0 - "POST /mcp HTTP/1.1" 503 Service Unavailable
1|mcp-brid | 2025-09-26T14:09:11: INFO:     127.0.0.1:39268 - "GET /healthz HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T14:09:11: INFO:     127.0.0.1:39274 - "GET /version HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T14:09:11: INFO:     92.20.131.75:0 - "GET /healthz HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T14:09:11: INFO:     92.20.131.75:0 - "GET /version HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T14:09:12: INFO:     92.20.131.75:0 - "GET /mcp HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T14:09:46: INFO:     92.20.131.75:0 - "POST /mcp HTTP/1.1" 502 Bad Gateway     
1|mcp-brid | 2025-09-26T14:12:20: INFO:     92.20.131.75:0 - "POST /mcp HTTP/1.1" 502 Bad Gateway     
1|mcp-brid | 2025-09-26T14:16:39: INFO:     92.20.131.75:0 - "POST /mcp HTTP/1.1" 202 Accepted        
1|mcp-brid | 2025-09-26T17:48:39: INFO:     127.0.0.1:50810 - "HEAD /mcp HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T17:48:39: INFO:     127.0.0.1:50822 - "GET /healthz HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T17:48:39: INFO:     127.0.0.1:50836 - "GET /version HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T18:24:26: INFO:     127.0.0.1:35348 - "HEAD /mcp HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T18:24:26: INFO:     127.0.0.1:35358 - "GET /healthz HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T18:24:26: INFO:     127.0.0.1:35372 - "GET /version HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T18:28:19: INFO:     127.0.0.1:40692 - "GET /debug/scan HTTP/1.1" 200 OK       
1|mcp-brid | 2025-09-26T18:28:36: INFO:     127.0.0.1:42800 - "GET /healthz HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T18:28:36: INFO:     127.0.0.1:42816 - "GET /version HTTP/1.1" 200 OK
1|mcp-brid | 2025-09-26T18:28:54: INFO:     92.20.131.75:0 - "POST /mcp HTTP/1.1" 301 Moved Permanently
1|mcp-brid | 2025-09-26T18:48:29: INFO:     92.20.131.75:0 - "HEAD /mem/sse HTTP/1.1" 405 Method Not Allowed
1|mcp-brid | 2025-09-26T22:57:20: INFO:     127.0.0.1:39958 - "GET /healthz HTTP/1.1" 500 Internal Server Error
1|mcp-brid | 2025-09-26T22:57:20: INFO:     127.0.0.1:39962 - "GET /version HTTP/1.1" 500 Internal Server Error
1|mcp-brid | 2025-09-26T22:57:20: INFO:     127.0.0.1:39976 - "GET /debug/upstream HTTP/1.1" 500 Internal Server Error
1|mcp-brid | 2025-09-26T22:57:20: INFO:     127.0.0.1:39982 - "GET /debug/scan HTTP/1.1" 500 Internal Server Error
1|mcp-brid | 2025-09-26T22:58:44: INFO:     127.0.0.1:43554 - "GET /healthz HTTP/1.1" 500 Internal Server Error
1|mcp-brid | 2025-09-26T22:58:44: INFO:     127.0.0.1:43570 - "GET /version HTTP/1.1" 500 Internal Server Error
1|mcp-brid | 2025-09-26T22:58:44: INFO:     127.0.0.1:43580 - "GET /mcp HTTP/1.1" 500 Internal Server Error
1|mcp-brid | 2025-09-26T22:58:44: INFO:     127.0.0.1:43588 - "GET /mcp HTTP/1.1" 500 Internal Server Error
1|mcp-brid | 2025-09-26T22:58:44: INFO:     127.0.0.1:43590 - "POST /mcp HTTP/1.1" 500 Internal Server Error

/home/gabri/dev/stelae/logs/mcp-bridge.err.log last 60 lines:
1|mcp-brid | 2025-09-26T22:58:44:     b"data=" + httpx.QueryParams({"data": raw.decode()}).encode(),  
1|mcp-brid | 2025-09-26T22:58:44:                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^     
1|mcp-brid | 2025-09-26T22:58:44: AttributeError: 'QueryParams' object has no attribute 'encode'      
1|mcp-brid | 2025-09-26T22:58:44: ERROR:    Exception in ASGI application
1|mcp-brid | 2025-09-26T22:58:44: Traceback (most recent call last):
1|mcp-brid | 2025-09-26T22:58:44:   File "/home/gabri/.venvs/stelae-bridge/lib/python3.12/site-packages/uvicorn/protocols/http/httptools_impl.py", line 401, in run_asgi
1|mcp-brid | 2025-09-26T22:58:44:     result = await app(  # type: ignore[func-returns-value]
1|mcp-brid | 2025-09-26T22:58:44:              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1|mcp-brid | 2025-09-26T22:58:44:   File "/home/gabri/.venvs/stelae-bridge/lib/python3.12/site-packages/uvicorn/middleware/proxy_headers.py", line 70, in __call__
1|mcp-brid | 2025-09-26T22:58:44:     return await self.app(scope, receive, send)
1|mcp-brid | 2025-09-26T22:58:44:            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1|mcp-brid | 2025-09-26T22:58:44:   File "/home/gabri/.venvs/stelae-bridge/lib/python3.12/site-packages/fastapi/applications.py", line 1054, in __call__
1|mcp-brid | 2025-09-26T22:58:44:     await super().__call__(scope, receive, send)
1|mcp-brid | 2025-09-26T22:58:44:   File "/home/gabri/.venvs/stelae-bridge/lib/python3.12/site-packages/starlette/applications.py", line 112, in __call__
1|mcp-brid | 2025-09-26T22:58:44:     await self.middleware_stack(scope, receive, send)
1|mcp-brid | 2025-09-26T22:58:44:   File "/home/gabri/.venvs/stelae-bridge/lib/python3.12/site-packages/starlette/middleware/errors.py", line 187, in __call__
1|mcp-brid | 2025-09-26T22:58:44:     raise exc
1|mcp-brid | 2025-09-26T22:58:44:   File "/home/gabri/.venvs/stelae-bridge/lib/python3.12/site-packages/starlette/middleware/errors.py", line 165, in __call__
1|mcp-brid | 2025-09-26T22:58:44:     await self.app(scope, receive, _send)
1|mcp-brid | 2025-09-26T22:58:44:   File "/home/gabri/.venvs/stelae-bridge/lib/python3.12/site-packages/starlette/middleware/cors.py", line 85, in __call__
1|mcp-brid | 2025-09-26T22:58:44:     await self.app(scope, receive, send)
1|mcp-brid | 2025-09-26T22:58:44:   File "/home/gabri/.venvs/stelae-bridge/lib/python3.12/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
1|mcp-brid | 2025-09-26T22:58:44:     await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
1|mcp-brid | 2025-09-26T22:58:44:   File "/home/gabri/.venvs/stelae-bridge/lib/python3.12/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
1|mcp-brid | 2025-09-26T22:58:44:     raise exc
1|mcp-brid | 2025-09-26T22:58:44:   File "/home/gabri/.venvs/stelae-bridge/lib/python3.12/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
1|mcp-brid | 2025-09-26T22:58:44:     await app(scope, receive, sender)
1|mcp-brid | 2025-09-26T22:58:44:   File "/home/gabri/.venvs/stelae-bridge/lib/python3.12/site-packages/starlette/routing.py", line 714, in __call__
1|mcp-brid | 2025-09-26T22:58:44:     await self.middleware_stack(scope, receive, send)
1|mcp-brid | 2025-09-26T22:58:44:   File "/home/gabri/.venvs/stelae-bridge/lib/python3.12/site-packages/starlette/routing.py", line 734, in app
1|mcp-brid | 2025-09-26T22:58:44:     await route.handle(scope, receive, send)
1|mcp-brid | 2025-09-26T22:58:44:   File "/home/gabri/.venvs/stelae-bridge/lib/python3.12/site-packages/starlette/routing.py", line 288, in handle
1|mcp-brid | 2025-09-26T22:58:44:     await self.app(scope, receive, send)
1|mcp-brid | 2025-09-26T22:58:44:   File "/home/gabri/.venvs/stelae-bridge/lib/python3.12/site-packages/starlette/routing.py", line 76, in app
1|mcp-brid | 2025-09-26T22:58:44:     await wrap_app_handling_exceptions(app, request)(scope, receive, send)
1|mcp-brid | 2025-09-26T22:58:44:   File "/home/gabri/.venvs/stelae-bridge/lib/python3.12/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
1|mcp-brid | 2025-09-26T22:58:44:     raise exc
1|mcp-brid | 2025-09-26T22:58:44:   File "/home/gabri/.venvs/stelae-bridge/lib/python3.12/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
1|mcp-brid | 2025-09-26T22:58:44:     await app(scope, receive, sender)
1|mcp-brid | 2025-09-26T22:58:44:   File "/home/gabri/.venvs/stelae-bridge/lib/python3.12/site-packages/starlette/routing.py", line 73, in app
1|mcp-brid | 2025-09-26T22:58:44:     response = await f(request)
1|mcp-brid | 2025-09-26T22:58:44:                ^^^^^^^^^^^^^^^^
1|mcp-brid | 2025-09-26T22:58:44:   File "/home/gabri/.venvs/stelae-bridge/lib/python3.12/site-packages/fastapi/routing.py", line 301, in app
1|mcp-brid | 2025-09-26T22:58:44:     raw_response = await run_endpoint_function(
1|mcp-brid | 2025-09-26T22:58:44:                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1|mcp-brid | 2025-09-26T22:58:44:   File "/home/gabri/.venvs/stelae-bridge/lib/python3.12/site-packages/fastapi/routing.py", line 212, in run_endpoint_function
1|mcp-brid | 2025-09-26T22:58:44:     return await dependant.call(**values)
1|mcp-brid | 2025-09-26T22:58:44:            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1|mcp-brid | 2025-09-26T22:58:44:   File "/home/gabri/dev/stelae/bridge/stream_http_bridge.py", line 355, in mcp_post
1|mcp-brid | 2025-09-26T22:58:44:     await ensure_config()
1|mcp-brid | 2025-09-26T22:58:44:   File "/home/gabri/dev/stelae/bridge/stream_http_bridge.py", line 215, in ensure_config
1|mcp-brid | 2025-09-26T22:58:44:     post_path, post_mode, results = await probe_post_endpoint(STATE.default_server)
1|mcp-brid | 2025-09-26T22:58:44:                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1|mcp-brid | 2025-09-26T22:58:44:   File "/home/gabri/dev/stelae/bridge/stream_http_bridge.py", line 183, in probe_post_endpoint
1|mcp-brid | 2025-09-26T22:58:44:     envelopes = build_envelopes(payload)
1|mcp-brid | 2025-09-26T22:58:44:                 ^^^^^^^^^^^^^^^^^^^^^^^^
1|mcp-brid | 2025-09-26T22:58:44:   File "/home/gabri/dev/stelae/bridge/stream_http_bridge.py", line 82, in build_envelopes
1|mcp-brid | 2025-09-26T22:58:44:     b"data=" + httpx.QueryParams({"data": raw.decode()}).encode(),  
1|mcp-brid | 2025-09-26T22:58:44:                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^     
1|mcp-brid | 2025-09-26T22:58:44: AttributeError: 'QueryParams' object has no attribute 'encode'      

---

gabri@Bladee:~/dev/stelae$ cat ~/.cloudflared/config.yml
tunnel: stelae
credentials-file: ~/.cloudflared/7a74f696-46b7-4573-b575-1ac25d038899.json

ingress:
  - hostname: mcp.infotopology.xyz
    service: http://localhost:9090   # <- bridge listens here
  - service: http_status:404

---

gabri@Bladee:~/dev/stelaesource ~/.nvm/nvm.sh && pm2 logs cloudflared --lines 80
[TAILING] Tailing last 80 lines for [cloudflared] process (change the value with --lines option)

# note: no output

---

gabri@Bladee:~/dev/stelae$ tree -L 2 /home/gabri/apps/mcp-proxy | sed -n '1,200p'
/home/gabri/apps/mcp-proxy
├── Dockerfile
├── LICENSE
├── Makefile
├── README.md
├── build
│   └── mcp-proxy
├── client.go
├── config.go
├── config.json
├── config_deprecated.go
├── docker-compose.yaml
├── docs
│   ├── CONFIGURATION.md
│   ├── DEPLOYMENT.md
│   ├── USAGE.md
│   └── index.html
├── go.mod
├── go.sums
├── http.go
└── main.go

3 directories, 18 files


# note: does this point you to the file you need?

---

gabri@Bladee:~/dev/stelae$ curl -skI https://mcp.infotopology.xyz/.well-known/mcp/manifest.json | sed -n '1,15p'
HTTP/2 530 
date: Fri, 26 Sep 2025 22:59:08 GMT
content-type: text/plain; charset=UTF-8
content-length: 16
cache-control: private, max-age=0, no-store, no-cache, must-revalidate, post-check=0, pre-check=0     
expires: Thu, 01 Jan 1970 00:00:01 GMT
referrer-policy: same-origin
x-frame-options: SAMEORIGIN
server: cloudflare
cf-ray: 98565ebd1967eed7-LHR
```
