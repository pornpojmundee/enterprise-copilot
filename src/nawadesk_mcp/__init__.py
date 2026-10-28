"""NawaDesk MCP server — the mock ticket system exposed as Model Context Protocol tools.

Any MCP client (our Action agent, Claude Desktop, VS Code, ...) can use it.
The acting employee is fixed when the server starts (NAWADESK_ACTING_EMPLOYEE_ID) and is
never a tool argument, so a model cannot act as someone else by changing parameters.
"""
