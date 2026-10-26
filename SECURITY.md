# Security Policy

## Supported versions

Only the latest commit on `main` receives security fixes.

## Reporting a vulnerability

Please do not open a public issue for security problems.

Report it privately through GitHub: **Security → Report a vulnerability** on this repository
(private vulnerability reporting). Include the affected file or tool, the steps to reproduce,
and the impact you observed. You should receive a first answer within 7 days.

## Deployment model

ADM1 Workbench is a **local, single-user** tool:

- The Streamlit webapp has no authentication and keeps one shared state file under
  `webapp/user_data/`. Do not expose it to a network you do not trust.
- The simulator MCP server (`simulator/mcp_server.py`) runs over stdio for a local MCP client.
  Its tools run simulations and can write files under `simulator/`. Only connect clients you trust.
