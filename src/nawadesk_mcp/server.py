"""NawaDesk MCP server (stdio).

    NAWADESK_ACTING_EMPLOYEE_ID=NT0082 python -m nawadesk_mcp.server

Claude Desktop / VS Code config example (see docs/action-agent.md):
    {"command": "<repo>/.venv/Scripts/python.exe", "args": ["-m", "nawadesk_mcp.server"],
     "env": {"NAWADESK_ACTING_EMPLOYEE_ID": "NT0082"}}
"""
from __future__ import annotations

import os
from functools import wraps
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from copilot.users import get_user

from .service import TicketError, TicketPermissionError, TicketService

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)


def build_server(employee_id: str) -> MCPServer:
    user = get_user(employee_id)
    svc = TicketService(user)
    server = MCPServer(
        name="NawaDesk",
        instructions=(f"Ticket system of Nawa Tech. You act as {user.name} ({user.employee_id}, role {user.app_role}). "
                      "Write tools change real data: show the user what you will do and get confirmation first."),
    )

    def safe(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except TicketPermissionError as e:
                raise ToolError(f"permission denied: {e}") from e
            except TicketError as e:
                raise ToolError(str(e)) from e
        return wrapper

    @server.tool(annotations=READ, description="Get one ticket (with comments) by ID, e.g. IT-1042. "
                                                "Only tickets the user is allowed to see are returned.")
    @safe
    def get_ticket(ticket_id: Annotated[str, Field(description="Ticket ID like IT-1042 or HR-0213")]) -> dict:
        return svc.get_ticket(ticket_id)

    @server.tool(annotations=READ, description="List the user's own tickets, newest first.")
    @safe
    def list_my_tickets(only_open: Annotated[bool, Field(description="Only tickets not yet resolved/closed")] = True) -> list[dict]:
        return svc.list_my_tickets(only_open)

    @server.tool(annotations=WRITE, description=(
        "Open a new IT or HR ticket on behalf of the user. Priority (IT-001 §2): P1 = core system down for many "
        "people, P2 = one person blocked with no workaround (e.g. notebook won't boot), P3 = normal issue with a "
        "workaround (password, Outlook), P4 = request/question (software install, documents)."))
    @safe
    def create_ticket(
        title: Annotated[str, Field(description="Short title in the user's language, max 120 chars")],
        description: Annotated[str, Field(description="What happened, what was tried, impact")],
        category: Literal["it", "hr"],
        subcategory: Annotated[str, Field(description=(
            "it: hardware-notebook, hardware-peripheral, account-password, network-vpn, email-outlook, "
            "software-request, access-request, security-phishing · hr: payroll, leave-correction, "
            "document-request, benefits"))],
        priority: Literal["P1", "P2", "P3", "P4"],
    ) -> dict:
        return svc.create_ticket(title, description, category, subcategory, priority)

    @server.tool(annotations=WRITE, description="Add a comment to a ticket the user can see (not closed).")
    @safe
    def add_comment(ticket_id: str, body: Annotated[str, Field(description="Comment text")]) -> dict:
        return svc.add_comment(ticket_id, body)

    @server.tool(annotations=WRITE, description=(
        "Change a ticket's status. Only support staff of the ticket's queue may do this; others get permission denied."))
    @safe
    def update_ticket_status(
        ticket_id: str,
        status: Literal["open", "in_progress", "waiting", "resolved", "closed"],
        resolution: Annotated[str, Field(description="Required when resolving/closing")] = "",
    ) -> dict:
        return svc.update_status(ticket_id, status, resolution)

    return server


def main() -> None:
    employee_id = os.getenv("NAWADESK_ACTING_EMPLOYEE_ID")
    if not employee_id:
        raise SystemExit("set NAWADESK_ACTING_EMPLOYEE_ID (the user this server acts for)")
    build_server(employee_id).run("stdio")


if __name__ == "__main__":
    main()
