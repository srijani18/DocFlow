# F1: Auth and workspaces (spec)

**Status:** Approved (2026-10-24)
**Phase:** 0
**Plan:** [plan.md](plan.md) · **Tasks:** [tasks.md](tasks.md)

## Summary

People can create an account, sign in and sign out. On first sign-in, each person automatically gets a **personal workspace** and is its **admin**. A workspace is the boundary for all data: nobody can see or change anything in a workspace they don't belong to. This feature also sets up the identity and access checks that every later feature relies on.

## Definitions

- **Workspace:** a tenant. All documents, jobs, extractions and settings belong to exactly one workspace.
- **Member:** a user with a membership in a workspace. A membership has exactly one role.
- **Roles:**
  - **admin:** everything a reviewer can do, plus managing workspace settings.
  - **reviewer:** works with documents.

| Action (✓ = allowed) | admin | reviewer | non-member |
|---|---|---|---|
| View workspace details | ✓ | ✓ | (looks like it doesn't exist) |
| Rename workspace | ✓ | | (looks like it doesn't exist) |

Permissions for later features (upload, review, export, webhooks, metrics) are set out in Decision Q3 below and confirmed in each feature's spec.

## User stories

- **US1:** As a new visitor, I want to create an account and sign in, so that I can use DocFlow.
- **US2:** As a new user, I want a workspace ready when I first sign in, so that I can start without any setup.
- **US3:** As a signed-in user, I want to see who I am signed in as, my workspace and my role, so that I know where my actions apply.
- **US4:** As a workspace admin, I want to rename my workspace, so that it has a meaningful name.
- **US5:** As a signed-in user, I want to sign out, so that nobody else using this browser can access my data.
- **US6:** As the operator, I want every access to workspace data to be checked against the caller's membership, so that data never leaks between workspaces.

## Acceptance criteria

### Sign-up, sign-in and sign-out

- **AC1:** WHEN a visitor without an account completes sign-up with valid details, THEN they are signed in and taken to the app home page.
- **AC2:** WHEN a returning user signs in with valid credentials, THEN they are taken to the app home page.
  WHEN the credentials are invalid, THEN they see an error message that doesn't say whether the account exists, and they stay signed out.
- **AC3:** WHEN a signed-out visitor opens any app page, THEN they are sent to the sign-in page, and after signing in they return to the page they originally asked for. This applies only to pages inside the app; any other return address is ignored and they go to the app home page.
- **AC4:** WHEN a user signs out, THEN their session ends in that browser, and opening any app page requires signing in again.

### Account provisioning

- **AC5:** WHEN a user makes their first authenticated request, THEN the system creates their user record, one personal workspace, and an admin membership for them in that workspace, all together or none at all.
- **AC6:** WHEN the same user makes further requests, including several "first" requests at the same moment, THEN no extra user, workspace or membership is ever created.
- **AC7:** WHEN the email address held by the identity provider has changed since the last request, THEN the stored email is updated on the next request.
- **AC8:** The personal workspace's default name is based on the user's display name, or the part of their email before the @ if there is no display name, or "My workspace" if neither is available. It is cut to the maximum name length if necessary.

### Identity

- **AC9:** WHEN an authenticated user asks who they are, THEN the system returns their user ID, email, display name and a list of their workspaces, with their role in each.
- **AC10:** WHEN a signed-in user opens the app home page, THEN it shows their email, their workspace's name and their role, and a sign-out control.

### API authentication

- **AC11:** WHEN a request to any protected endpoint has a credential that is missing, malformed or expired, has an invalid signature, was issued by a different issuer or for a different audience, belongs to an anonymous (not signed-in) session, or is signed with a disallowed algorithm, THEN the request is rejected as unauthenticated, and no data is returned, created or changed.
- **AC12:** WHEN the identity provider starts signing with a new key, THEN tokens signed with that key are accepted without restarting or redeploying the backend.
  WHEN a key is withdrawn, THEN tokens signed with it are rejected within 10 minutes.
- **AC13:** WHEN the identity provider's key endpoint can't be reached:
  - and keys were fetched successfully before, THEN valid tokens are still accepted;
  - and keys were never fetched, THEN the request fails with a "temporarily unavailable" error that suggests retrying, not with "unauthenticated".

### Workspace access

- **AC14:** WHEN a member asks for their workspace's details, THEN they receive the workspace's ID, name and their own role.
- **AC15:** WHEN a user asks for a workspace they are not a member of, whether or not it exists, THEN the response is "not found", identical in both cases.
- **AC16:** WHEN an admin renames their workspace with a valid name (1–80 characters after trimming surrounding spaces), THEN the trimmed name is saved and returned.
- **AC17:** WHEN a reviewer tries to rename their workspace, THEN the request is rejected as forbidden and the name doesn't change.
- **AC18:** WHEN a rename has a name that is empty, only whitespace or over 80 characters, THEN it is rejected with a validation error that names the field, and the name doesn't change.
- **AC19:** For every workspace-scoped operation in this feature, an automated test proves that a member of workspace A can't read, change or detect workspace B.

### Availability

- **AC20:** WHEN a signed-in user opens the app and the backend is starting up or temporarily unreachable, THEN the app shows a "starting up" message and retries automatically for up to 90 seconds. If the backend is still unavailable after that, it shows an error with a "Try again" button.

## Edge cases

- **Several first requests at once** (for example, two browser tabs): exactly one user and one workspace are created (AC6).
- **No email in the token** (some sign-in methods): the user is created with no email, and the workspace name falls back as in AC8.
- **Very long or non-Latin display names:** the default workspace name is cut to 80 characters without splitting a character.
- **Clock skew** between the identity provider and our servers: a small tolerance of up to 30 seconds on token time checks.
- **Expired session while the app is open:** the app refreshes the session silently. If that fails, the user is sent to sign-in and then returned to the same page (AC3).
- **Signed out in another tab:** the next request from any other tab sends the user to sign-in.
- **A user with no memberships** (not possible in F1, but possible once removing members exists): the identity response returns an empty list, and the app shows "You don't belong to a workspace yet."
- **A request naming a malformed workspace ID:** treated as "not found" (AC15), not as a validation error. That way, malformed and unknown IDs can't be told apart.
- **An account deleted at the identity provider while a token is still valid:** the token is accepted until it expires, up to 1 hour. Revoking it immediately is a non-goal.
- **Backend and database both waking from sleep:** the first request may take up to about 60 seconds. This is covered by AC20.

## Non-goals

- Inviting members, removing members or changing roles. The data model supports several members per workspace, but there is no UI or API for it yet.
- Switching between several workspaces in the UI.
- Deleting workspaces or accounts, or transferring ownership.
- Password reset, email verification and magic links. These need an email sender we don't have yet (see Q1 and Q6).
- Multi-factor authentication, single sign-on (SSO/SAML) and immediately revoking active sessions.
- Profile editing.
- Rate limiting and audit logging of sign-ins (F14).

## Decisions (formerly open questions, resolved 2026-10-24)

- **Q1. Sign-in methods:** email and password, with email confirmation turned off. The identity provider's built-in email sender reaches only the project owner's team, so confirmation would block outside users. "Continue with GitHub" can be added later as a small follow-up.
- **Q2. Naming the workspace in requests:** in the URL path, `/workspaces/{id}/…`.
- **Q3. Role permissions for later features:** reviewers can upload, view, search, review, approve and export. Admins can also rename the workspace, manage webhooks and see the cost and metrics pages. Each later spec confirms its own rows.
- **Q4. End-to-end sign-in test:** a Playwright smoke test against the deployed site, using a dedicated test account whose credentials are GitHub secrets. It runs manually and after each production deploy.
- **Q5. Default workspace name:** "{name}'s workspace" (AC8).
- **Q6. Password reset:** deferred until there is an email sender (Phase 5, optional).
