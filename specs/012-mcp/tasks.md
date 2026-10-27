# F12: MCP server (tasks)

**Status:** Approved (2026-10-28)
**Prerequisite:** F8 (search), F7 (approved versions).

- [ ] **F12-T1: Access tokens** (AC1–AC3): migration `0012_api_tokens`, create/list/revoke endpoints, hashing and verification, tests.
- [ ] **F12-T2: MCP server and auth** (AC4, AC6, AC7): `MCPServer` mounted at `/mcp`, `WorkspaceTokenVerifier`, protected-resource metadata, logging, SDK client tests.
- [ ] **F12-T3: Tools** (AC5, AC8): `search_documents`, `get_document`, `list_vendors`, `spend_summary`, with integration tests on seeded data.
- [ ] **F12-T4: Settings panel:** token list, create (shown once, with client snippets), revoke.
- [ ] **F12-T5: Live check and close-out:** Claude Code connected locally answers a spend question with the dev workspace's data; README section "Use DocFlow from your AI assistant"; spec status `Implemented`.
