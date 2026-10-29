"""squad-hub-plus: the repo-only companion of squad-hub.

Everything squad-hub cannot do inside the Hermes Desktop plugin SDK lives in this package's Desktop half
(`desktop/plugin.js`): floating layout sides, hiding the profile rail and the Bots tab, opening `.env` files from
the file tree, creating and removing git worktrees, the native multi-folder picker and the Kanban page's own board
preselection. squad-hub dispatches `squad-hub:<action>` DOM events for those; this plugin takes them over.

The agent half is deliberately empty: this package exists for its Desktop half, and `register` only has to be there
so the plugin loads like any other.
"""
from __future__ import annotations


def register(ctx) -> None:
    """No agent-side contribution: the Desktop half does the work."""
    return None
