# F12: MCP server (spec)

**Status:** Draft (2026-10-27)
**Phase:** 6
**Plan:** [plan.md](plan.md) · **Tasks:** [tasks.md](tasks.md)

## Summary

A workspace's documents become available to AI assistants (Claude Code, Claude Desktop, Cursor, VS Code and other MCP clients) through a **Model Context Protocol** server at `/mcp`. An assistant can search the documents, read one document's extracted data, list vendors, and add up spend, so that a member can ask "how much did we spend with Kaveri last quarter?" in the assistant they already use.

The server is **read-only**. It acts as one member of one workspace, through an **access token** the member creates in Settings and can revoke at any time.

## User stories

- **US1:** As a member, I want to connect my AI assistant to my workspace, so that I can ask questions about our documents without opening DocFlow.
- **US2:** As a member, I want answers about spend to add up only approved, correctly totalled data, never mixing currencies, so that I can trust them.
- **US3:** As an admin, I want to see and revoke every access token in the workspace, so that I control who reaches its data from outside.
- **US4:** As the operator, I want MCP access to be impossible without a valid token, and limited to the token's workspace, so that it adds no new way in.

## Acceptance criteria

### Access tokens

- **AC1:** WHEN a member creates an access token in **Settings → AI assistants (MCP)**, with a name and an expiry (30 days, 90 days or 1 year), THEN the token is shown **once**, with a copy button and a ready-to-paste client configuration. Afterwards only its name, its first 8 characters, its creator, creation date, last use and expiry are shown.
- **AC2:** A token is stored only as a hash. It works only for its own workspace, only while it is unexpired and unrevoked, and only while its creator is still a member; it acts with that member's identity, read-only.
- **AC3:** A member sees and revokes their own tokens. An admin sees and revokes every token in the workspace. Revoking takes effect on the next request.

### The MCP server

- **AC4:** `/mcp` speaks MCP over **Streamable HTTP**. A request without a valid token gets **401** with a `WWW-Authenticate` header pointing at the server's protected-resource metadata (MCP authorization spec). A revoked, expired or other-workspace token gets 401 too, with no hint of which.
- **AC5:** The server offers four read-only tools, each with a description and a JSON input schema:
  - **`search_documents`:** the F8 hybrid search, with its filters (type, status, vendor, dates, amounts) and a limit of at most 20. Returns each document's id, file name, type, status, vendor, date, total, currency, the search snippet and a link to it in DocFlow.
  - **`get_document`:** one document's status, type, vendor, date, total, currency, the **approved** extraction if there is one (otherwise the current one, marked "not yet approved"), its open validation issues, and its link.
  - **`list_vendors`:** vendors with their document count, last document date and totals per currency, optionally filtered by a name fragment.
  - **`spend_summary`:** totals grouped by vendor, month or document type, over a date range, optionally for one vendor. **Approved documents only** by default; totals are **per currency** and never converted or added across currencies.
- **AC6:** Every tool sees only the token's workspace. A document id from another workspace returns "not found", the same as an id that doesn't exist.
- **AC7:** Each tool call is logged with the tool name, workspace, token id, duration and result count, but **not** its arguments or results (search text and document data stay out of logs, constitution §6.5).
- **AC8:** `search_documents` uses the workspace's own AI key for the query embedding (F15). Without one, it falls back to keyword matches and says so in its result, as the web search does.

## Edge cases

- **A token pasted into the wrong place** (e.g. a chat): the member revokes it in Settings; tokens start with `dfw_` so secret scanners (GitHub, gitleaks) can be taught to spot them.
- **Large results:** search returns at most 20 documents; `get_document` returns one extraction (line items included); summaries return at most 100 groups.
- **The member is removed from the workspace:** their tokens stop working immediately (AC2) and are listed as "inactive" to admins.
- **Free Render instance asleep:** the first MCP request takes about a minute (as for the web app); clients show it as slow, not failed.

## Non-goals

- Writing through MCP: approving, correcting, uploading or deleting documents.
- OAuth sign-in from the assistant (Supabase's OAuth 2.1 server); see D2.
- MCP resources and prompts; tools only.
- Per-token scopes beyond read-only.

## Decisions (proposed)

- **D1. Mounted in the API process** at `/mcp` (overview §3, ADR-0002), with the official **MCP Python SDK 2.3** (`MCPServer`, stateless Streamable HTTP, JSON responses). No second service, no extra cold start.
- **D2. Workspace access tokens, not OAuth, for now.** MCP clients that take a header (Claude Code, Claude Desktop through `mcp-remote`, Cursor, VS Code) work with a bearer token, which needs nothing beyond our own database and is easy to explain, test and revoke. OAuth through Supabase's OAuth 2.1 server would let web connectors (claude.ai) sign in without copying a token. But it needs a consent page, dynamic client registration and a choice of workspace at sign-in, and Supabase doesn't say whether the free plan includes it. The SDK's `TokenVerifier` is the single place a Supabase OAuth token could be accepted later, so this choice doesn't block it.
- **D3. Read-only, approved-first.** Answers prefer what a person or the agent approved; unapproved data is labelled as such. Spend sums approved documents only, per currency.
- **D4. Tools reuse the feature services** (search, documents, extractions, validation), not new SQL, except `list_vendors` and `spend_summary`, which are new aggregate queries on the typed `documents` columns (ADR-0005 §4).
