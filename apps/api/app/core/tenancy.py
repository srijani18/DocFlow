"""Workspace scoping (constitution §4).

A `WorkspaceScope` is proof that the caller is a member of a workspace. Repository
functions for tenant data take one as their first argument and filter by its
`workspace_id`; the only ways to get one are the membership-checking dependency
(`require_workspace_member`) and, from F3, a job record.
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkspaceScope:
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    role: str
