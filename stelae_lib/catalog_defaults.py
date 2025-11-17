from __future__ import annotations

from typing import Any, Dict, List

DEFAULT_CUSTOM_TOOLS: Dict[str, Any] = {
    "tools": [],
}

DEFAULT_TOOL_OVERRIDES: Dict[str, Any] = {
    "schemaVersion": 2,
    "master": {"tools": {"*": {"annotations": {}}}},
    "servers": {
        "integrator": {
            "enabled": True,
            "tools": {
                "manage_stelae": {
                    "enabled": True,
                    "inputSchema": {
                        "properties": {
                            "operation": {"title": "Operation", "type": "string"},
                            "params": {
                                "anyOf": [
                                    {"additionalProperties": True, "type": "object"},
                                    {"type": "null"},
                                ],
                                "default": None,
                                "title": "Params",
                            },
                        },
                        "required": ["operation"],
                        "type": "object",
                    },
                    "outputSchema": {
                        "properties": {
                            "result": {
                                "additionalProperties": True,
                                "title": "Result",
                                "type": "object",
                            }
                        },
                        "required": ["result"],
                        "type": "object",
                    },
                }
            },
        },
        "one_mcp": {
            "enabled": True,
            "tools": {
                "configure_mcp_plan": {"enabled": False, "inputSchema": {"type": "object"}},
                "deep_search_planning": {"enabled": False, "inputSchema": {"type": "object"}},
                "fetch_readme": {
                    "enabled": False,
                    "inputSchema": {
                        "properties": {"github_url": {"title": "Github Url", "type": "string"}},
                        "required": ["github_url"],
                        "type": "object",
                    },
                },
                "file_system_config_setup": {"enabled": False, "inputSchema": {"type": "object"}},
                "find_mcp_config_path_path": {
                    "enabled": False,
                    "inputSchema": {
                        "properties": {
                            "application": {
                                "enum": ["Cursor", "Claude"],
                                "title": "Application",
                                "type": "string",
                            },
                            "os": {
                                "default": "Mac",
                                "enum": ["Mac", "Windows"],
                                "title": "Os",
                                "type": "string",
                            },
                        },
                        "required": ["application"],
                        "type": "object",
                    },
                },
                "quick_search": {
                    "enabled": False,
                    "inputSchema": {
                        "properties": {
                            "query": {"title": "Query", "type": "string"},
                            "top_k": {"default": 100, "title": "Top K", "type": "integer"},
                        },
                        "required": ["query"],
                        "type": "object",
                    },
                },
                "validate_mcp_config_content": {
                    "enabled": False,
                    "inputSchema": {
                        "properties": {
                            "mcp_config_content": {"title": "Mcp Config Content", "type": "string"}
                        },
                        "required": ["mcp_config_content"],
                        "type": "object",
                    },
                },
            },
        },
        "public_mcp_catalog": {
            "enabled": True,
            "metadata": {
                "description": "Remote 1mcp discovery endpoint exposed over HTTP/SSE.",
                "source": "https://github.com/Dub1n/stelae-1mcpserver",
            },
            "tools": {
                "deep_search": {
                    "description": "Plan requirements and auto-select compatible MCP servers.",
                    "enabled": True,
                },
                "list_servers": {
                    "description": "Return server descriptors and setup guidance.",
                    "enabled": True,
                },
            },
        },
        "tool_aggregator": {"enabled": True, "tools": {}},
        "facade": {"enabled": True, "tools": {"search": {"enabled": False}}},
    },
}

DEFAULT_DISCOVERED_SERVERS: List[Dict[str, Any]] = [
    {
        "name": "apecloud-aperag",
        "transport": "metadata",
        "description": "Production-ready RAG platform combining Graph RAG, vector search, and full-text search. Best choice for building your own Knowledge Graph and for Context Engineering",
        "source": "https://github.com/apecloud/ApeRAG",
        "options": {
            "sourceType": "1mcp-search",
            "originalName": "apecloud/ApeRAG",
            "score": 0.3366216216216216,
            "query": "vector search search",
        },
        "tools": [],
    },
    {
        "name": "blazickjp-arxiv-mcp-server",
        "transport": "metadata",
        "description": "Search ArXiv research papers",
        "source": "https://github.com/blazickjp/arxiv-mcp-server",
        "options": {
            "sourceType": "1mcp-search",
            "originalName": "blazickjp/arxiv-mcp-server",
            "score": 0.3091666666666667,
            "query": "vector search search",
        },
        "tools": [],
    },
    {
        "name": "himalayas-app-himalayas-mcp",
        "transport": "metadata",
        "description": "Access tens of thousands of remote job listings and company information. This public MCP server provides real-time access to Himalayas' remote jobs database.",
        "source": "https://github.com/Himalayas-App/himalayas-mcp",
        "options": {
            "sourceType": "1mcp-search",
            "originalName": "Himalayas-App/himalayas-mcp",
            "score": 0.24290043290043292,
            "query": "public mcp catalog",
        },
        "tools": [],
    },
    {
        "name": "kashiwabyte-vikingdb-mcp-server",
        "transport": "metadata",
        "description": "VikingDB integration with collection and index introduction, vector store and search capabilities.",
        "source": "https://github.com/KashiwaByte/vikingdb-mcp-server",
        "options": {
            "sourceType": "1mcp-search",
            "originalName": "KashiwaByte/vikingdb-mcp-server",
            "score": 0.39699537750385205,
            "query": "vector search search",
        },
        "tools": [],
    },
    {
        "name": "notion",
        "transport": "metadata",
        "description": "Notion official MCP server",
        "source": "https://github.com/makenotion/notion-mcp-server",
        "options": {
            "sourceType": "1mcp-search",
            "originalName": "Notion",
            "score": 0.22348484848484848,
            "query": "public mcp catalog",
        },
        "tools": [],
    },
    {
        "name": "pab1ito-chess-mcp",
        "transport": "metadata",
        "description": "Access Chess.com player data, game records, and other public information through standardized MCP interfaces, allowing AI assistants to search and analyze chess information.",
        "source": "https://github.com/pab1it0/chess-mcp",
        "options": {
            "sourceType": "1mcp-search",
            "originalName": "pab1ito/chess-mcp",
            "score": 0.24146438204029827,
            "query": "public mcp catalog",
        },
        "tools": [],
    },
    {
        "name": "public_mcp_catalog",
        "transport": "http",
        "url": "https://mcp.1mcpserver.com/mcp/",
        "headers": {
            "Accept": "text/event-stream",
            "Cache-Control": "no-store",
        },
        "description": "Remote 1mcp discovery endpoint exposed over HTTP/SSE.",
        "source": "https://github.com/Dub1n/stelae-1mcpserver",
        "tools": [
            {"name": "deep_search", "description": "Plan requirements and auto-select compatible MCP servers."},
            {"name": "list_servers", "description": "Return server descriptors and setup guidance."},
        ],
        "requiresAuth": False,
        "options": {
            "enableAsync": False,
        },
    },
    {
        "name": "qdrant",
        "transport": "stdio",
        "description": "Implement semantic memory layer on top of the Qdrant vector search engine",
        "source": "https://github.com/qdrant/mcp-server-qdrant/",
        "options": {
            "sourceType": "1mcp-search",
            "originalName": "Qdrant",
            "score": 0.3905913978494624,
            "query": "vector search search",
            "hydratedFrom": "catalog_overrides",
            "hydrated": True,
        },
        "tools": [],
        "command": "uvx",
        "args": ["mcp-server-qdrant", "--transport", "stdio"],
        "env": {
            "COLLECTION_NAME": "{{QDRANT_COLLECTION_NAME}}",
            "QDRANT_LOCAL_PATH": "{{QDRANT_LOCAL_PATH}}",
            "EMBEDDING_MODEL": "{{QDRANT_EMBEDDING_MODEL}}",
        },
    },
    {
        "name": "sirmews-mcp-pinecone",
        "transport": "metadata",
        "description": "Pinecone integration with vector search capabilities",
        "source": "https://github.com/sirmews/mcp-pinecone",
        "options": {
            "sourceType": "1mcp-search",
            "originalName": "sirmews/mcp-pinecone",
            "score": 0.5083333333333333,
            "query": "vector search search",
        },
        "tools": [],
    },
]

DEFAULT_TOOL_AGGREGATIONS: Dict[str, Any] = {
    "schemaVersion": 1,
    "defaults": {
        "selectorField": "operation",
        "caseInsensitiveSelector": True,
        "timeoutSeconds": 60,
        "serverName": "tool_aggregator",
    },
    "hiddenTools": [
        {"server": "one_mcp", "tool": "configure_mcp_plan", "reason": "Use manage_stelae integrator instead"},
        {"server": "one_mcp", "tool": "deep_search_planning", "reason": "Use manage_stelae integrator instead"},
        {"server": "one_mcp", "tool": "fetch_readme", "reason": "Use manage_stelae integrator instead"},
        {"server": "one_mcp", "tool": "file_system_config_setup", "reason": "Use manage_stelae integrator instead"},
        {"server": "one_mcp", "tool": "find_mcp_config_path_path", "reason": "Use manage_stelae integrator instead"},
        {"server": "one_mcp", "tool": "quick_search", "reason": "Use manage_stelae integrator instead"},
        {"server": "one_mcp", "tool": "validate_mcp_config_content", "reason": "Use manage_stelae integrator instead"},
        {"server": "facade", "tool": "search", "reason": "Placeholder verification tool no longer needed in manifests"},
    ],
    "aggregations": [],
    "proxyURL": "http://127.0.0.1:9090",
}

DEFAULT_CATALOG_FRAGMENT: Dict[str, Any] = {
    "tool_overrides": DEFAULT_TOOL_OVERRIDES,
    "tool_aggregations": DEFAULT_TOOL_AGGREGATIONS,
    "hide_tools": [],
}
