"""
MCP Server wrapping Google Workspace CLI (gws)
Exposes gws commands as MCP tools over Streamable HTTP transport.

Usage:
    pip install fastmcp
    gws auth login -s drive,gmail,calendar,sheets,docs
    python server.py --port 8000
    # Connect your agent to http://YOUR_HOST:8000/mcp
"""

import asyncio
import json
import logging
import os
import shutil
import argparse

from fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gws-mcp")

GWS_BIN = shutil.which("gws")
if not GWS_BIN:
    logger.warning("gws not found on PATH. Install with: npm install -g @googleworkspace/cli")


async def run_gws(
    *args: str,
    input_data: str | None = None,
    page_all: bool = False,
    page_limit: int | None = None,
    page_delay: int | None = None,
    output_format: str | None = None,
    dry_run: bool = False,
    upload_path: str | None = None,
    output_path: str | None = None,
) -> dict | str:
    """Execute a gws CLI command and return the result."""
    cmd = [GWS_BIN or "gws", *args]
    if page_all:
        cmd.append("--page-all")
    if page_limit is not None:
        cmd.extend(["--page-limit", str(page_limit)])
    if page_delay is not None:
        cmd.extend(["--page-delay", str(page_delay)])
    if output_format:
        cmd.extend(["--format", output_format])
    if dry_run:
        cmd.append("--dry-run")
    if upload_path:
        cmd.extend(["--upload", upload_path])
    if output_path:
        cmd.extend(["-o", output_path])

    logger.info(f"Running: {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE if input_data else None,
    )
    stdout, stderr = await proc.communicate(input=input_data.encode() if input_data else None)
    output = stdout.decode().strip()
    err = stderr.decode().strip()

    if proc.returncode != 0:
        return {"error": err or output or f"gws exited with code {proc.returncode}", "returncode": proc.returncode}
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return output if output else {"message": "OK", "stderr": err}


mcp = FastMCP(
    name="gws-mcp",
    instructions=(
        "Google Workspace MCP Server wrapping the gws CLI. "
        "Provides tools for Gmail, Drive, Calendar, Sheets, Docs, Slides, Tasks, People, "
        "Chat, Classroom, Forms, Keep, Meet, Events, Admin Reports, Model Armor, and Workflows. "
        "All responses are structured JSON from the Google Workspace APIs. "
        "Use gws_schema to discover API method parameters before calling gws_raw."
    ),
)


# ========================== GMAIL ==========================


@mcp.tool()
async def gmail_list_messages(query: str = "", max_results: int = 10) -> dict | str:
    """Search/list Gmail messages.

    Args:
        query: Gmail search query (e.g. 'is:unread', 'from:user@example.com').
        max_results: Maximum number of messages to return.
    """
    params = {"maxResults": max_results, "userId": "me"}
    if query:
        params["q"] = query
    return await run_gws("gmail", "users", "messages", "list", "--params", json.dumps(params))


@mcp.tool()
async def gmail_get_message(message_id: str) -> dict | str:
    """Get a specific Gmail message by ID.

    Args:
        message_id: The Gmail message ID.
    """
    return await run_gws("gmail", "users", "messages", "get", "--params", json.dumps({"userId": "me", "id": message_id, "format": "full"}))


@mcp.tool()
async def gmail_send(to: str, subject: str, body: str) -> dict | str:
    """Send an email via Gmail using the +send helper.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Email body text (plain text).
    """
    return await run_gws("gmail", "+send", "--to", to, "--subject", subject, "--body", body)


@mcp.tool()
async def gmail_triage(max_messages: int = 20, query: str = "", labels: bool = False) -> dict | str:
    """Show unread inbox summary (sender, subject, date) using +triage helper.

    Args:
        max_messages: Maximum messages to show.
        query: Gmail search query (default: is:unread).
        labels: Include label names in output.
    """
    args = ["gmail", "+triage", "--max", str(max_messages)]
    if query:
        args.extend(["--query", query])
    if labels:
        args.append("--labels")
    return await run_gws(*args)


@mcp.tool()
async def gmail_watch(project: str, label_ids: str = "", once: bool = False, cleanup: bool = False, subscription: str = "") -> dict | str:
    """Watch for new emails and stream them as NDJSON using +watch helper.

    Args:
        project: GCP project ID for Pub/Sub resources.
        label_ids: Comma-separated Gmail label IDs to filter (e.g. INBOX,UNREAD).
        once: Pull once and exit.
        cleanup: Delete created Pub/Sub resources on exit.
        subscription: Existing Pub/Sub subscription name (skip setup).
    """
    args = ["gmail", "+watch"]
    if subscription:
        args.extend(["--subscription", subscription])
    else:
        args.extend(["--project", project])
    if label_ids:
        args.extend(["--label-ids", label_ids])
    if once:
        args.append("--once")
    if cleanup:
        args.append("--cleanup")
    return await run_gws(*args)


@mcp.tool()
async def gmail_list_labels() -> dict | str:
    """List all Gmail labels."""
    return await run_gws("gmail", "users", "labels", "list", "--params", json.dumps({"userId": "me"}))


@mcp.tool()
async def gmail_modify_message(message_id: str, add_labels: list[str] | None = None, remove_labels: list[str] | None = None) -> dict | str:
    """Modify labels on a Gmail message (e.g. mark read/unread, archive).

    Args:
        message_id: The Gmail message ID.
        add_labels: Label IDs to add.
        remove_labels: Label IDs to remove.
    """
    body = {}
    if add_labels:
        body["addLabelIds"] = add_labels
    if remove_labels:
        body["removeLabelIds"] = remove_labels
    return await run_gws("gmail", "users", "messages", "modify", "--params", json.dumps({"userId": "me", "id": message_id}), "--json", json.dumps(body))


@mcp.tool()
async def gmail_list_threads(query: str = "", max_results: int = 10) -> dict | str:
    """List Gmail threads.

    Args:
        query: Gmail search query.
        max_results: Maximum threads to return.
    """
    params: dict = {"maxResults": max_results, "userId": "me"}
    if query:
        params["q"] = query
    return await run_gws("gmail", "users", "threads", "list", "--params", json.dumps(params))


@mcp.tool()
async def gmail_get_thread(thread_id: str) -> dict | str:
    """Get a Gmail thread by ID.

    Args:
        thread_id: The thread ID.
    """
    return await run_gws("gmail", "users", "threads", "get", "--params", json.dumps({"userId": "me", "id": thread_id}))


# ========================== DRIVE ==========================


@mcp.tool()
async def drive_list_files(query: str = "", max_results: int = 10, order_by: str = "modifiedTime desc") -> dict | str:
    """List/search files in Google Drive.

    Args:
        query: Drive search query (e.g. "name contains 'report'").
        max_results: Maximum files to return.
        order_by: Sort order.
    """
    params = {"pageSize": max_results, "orderBy": order_by, "fields": "files(id,name,mimeType,modifiedTime,size,webViewLink)"}
    if query:
        params["q"] = query
    return await run_gws("drive", "files", "list", "--params", json.dumps(params))


@mcp.tool()
async def drive_get_file(file_id: str) -> dict | str:
    """Get metadata for a Drive file.

    Args:
        file_id: The file ID.
    """
    return await run_gws("drive", "files", "get", "--params", json.dumps({"fileId": file_id, "fields": "id,name,mimeType,modifiedTime,size,webViewLink,description,owners"}))


@mcp.tool()
async def drive_create_file(name: str, mime_type: str = "application/vnd.google-apps.document", parent_folder_id: str = "") -> dict | str:
    """Create a new file in Google Drive.

    Args:
        name: File name.
        mime_type: MIME type (e.g. 'application/vnd.google-apps.document').
        parent_folder_id: Parent folder ID (optional).
    """
    body: dict = {"name": name, "mimeType": mime_type}
    if parent_folder_id:
        body["parents"] = [parent_folder_id]
    return await run_gws("drive", "files", "create", "--json", json.dumps(body))


@mcp.tool()
async def drive_upload(file_path: str, parent: str = "", name: str = "") -> dict | str:
    """Upload a file to Drive with automatic metadata using +upload helper.

    Args:
        file_path: Path to file to upload.
        parent: Parent folder ID (optional).
        name: Target filename (defaults to source filename).
    """
    args = ["drive", "+upload", file_path]
    if parent:
        args.extend(["--parent", parent])
    if name:
        args.extend(["--name", name])
    return await run_gws(*args)


@mcp.tool()
async def drive_list_permissions(file_id: str) -> dict | str:
    """List permissions on a Drive file or shared drive.

    Args:
        file_id: The file or drive ID.
    """
    return await run_gws("drive", "permissions", "list", "--params", json.dumps({"fileId": file_id}))


@mcp.tool()
async def drive_create_permission(file_id: str, role: str, type: str, email_address: str = "") -> dict | str:
    """Share a Drive file by creating a permission.

    Args:
        file_id: The file ID.
        role: Permission role: owner, organizer, fileOrganizer, writer, commenter, reader.
        type: Grantee type: user, group, domain, anyone.
        email_address: Email of user or group (required for type=user/group).
    """
    body: dict = {"role": role, "type": type}
    if email_address:
        body["emailAddress"] = email_address
    return await run_gws("drive", "permissions", "create", "--params", json.dumps({"fileId": file_id}), "--json", json.dumps(body))


@mcp.tool()
async def drive_delete_permission(file_id: str, permission_id: str) -> dict | str:
    """Remove a permission from a Drive file.

    Args:
        file_id: The file ID.
        permission_id: The permission ID.
    """
    return await run_gws("drive", "permissions", "delete", "--params", json.dumps({"fileId": file_id, "permissionId": permission_id}))


@mcp.tool()
async def drive_list_shared_drives(max_results: int = 10) -> dict | str:
    """List shared drives.

    Args:
        max_results: Maximum shared drives to return.
    """
    return await run_gws("drive", "drives", "list", "--params", json.dumps({"pageSize": max_results}))


@mcp.tool()
async def drive_list_comments(file_id: str, max_results: int = 20) -> dict | str:
    """List comments on a Drive file.

    Args:
        file_id: The file ID.
        max_results: Max comments to return.
    """
    return await run_gws("drive", "comments", "list", "--params", json.dumps({"fileId": file_id, "pageSize": max_results, "fields": "comments(id,content,author,createdTime,resolved)"}))


# ========================== CALENDAR ==========================


@mcp.tool()
async def calendar_list_events(time_min: str = "", time_max: str = "", max_results: int = 10, calendar_id: str = "primary") -> dict | str:
    """List upcoming calendar events.

    Args:
        time_min: Start time in RFC3339 (defaults to now).
        time_max: End time in RFC3339 (optional).
        max_results: Maximum events.
        calendar_id: Calendar ID (default 'primary').
    """
    from datetime import datetime, timezone
    params: dict = {"calendarId": calendar_id, "maxResults": max_results, "singleEvents": True, "orderBy": "startTime"}
    params["timeMin"] = time_min or datetime.now(timezone.utc).isoformat()
    if time_max:
        params["timeMax"] = time_max
    return await run_gws("calendar", "events", "list", "--params", json.dumps(params))


@mcp.tool()
async def calendar_insert(summary: str, start: str, end: str, description: str = "", location: str = "", attendees: str = "", calendar_id: str = "primary") -> dict | str:
    """Create a new calendar event using +insert helper.

    Args:
        summary: Event title.
        start: Start time (ISO 8601, e.g. 2026-03-10T09:00:00+07:00).
        end: End time (ISO 8601).
        description: Event description.
        location: Event location.
        attendees: Comma-separated attendee emails.
        calendar_id: Calendar ID (default: primary).
    """
    args = ["calendar", "+insert", "--summary", summary, "--start", start, "--end", end]
    if calendar_id != "primary":
        args.extend(["--calendar", calendar_id])
    if description:
        args.extend(["--description", description])
    if location:
        args.extend(["--location", location])
    if attendees:
        for email in attendees.split(","):
            args.extend(["--attendee", email.strip()])
    return await run_gws(*args)


@mcp.tool()
async def calendar_agenda(today: bool = False, tomorrow: bool = False, week: bool = False, days: int = 0, calendar: str = "") -> dict | str:
    """Show upcoming events across all calendars using +agenda helper.

    Args:
        today: Show today's events only.
        tomorrow: Show tomorrow's events only.
        week: Show this week's events.
        days: Number of days ahead to show.
        calendar: Filter to specific calendar name or ID.
    """
    args = ["calendar", "+agenda"]
    if today:
        args.append("--today")
    elif tomorrow:
        args.append("--tomorrow")
    elif week:
        args.append("--week")
    elif days:
        args.extend(["--days", str(days)])
    if calendar:
        args.extend(["--calendar", calendar])
    return await run_gws(*args)


@mcp.tool()
async def calendar_delete_event(event_id: str, calendar_id: str = "primary") -> dict | str:
    """Delete a calendar event.

    Args:
        event_id: The event ID.
        calendar_id: Calendar ID.
    """
    return await run_gws("calendar", "events", "delete", "--params", json.dumps({"calendarId": calendar_id, "eventId": event_id}))


@mcp.tool()
async def calendar_quick_add(text: str, calendar_id: str = "primary") -> dict | str:
    """Create a calendar event from natural language text.

    Args:
        text: Quick-add text (e.g. 'Meeting with Bob tomorrow 3pm').
        calendar_id: Calendar ID.
    """
    return await run_gws("calendar", "events", "quickAdd", "--params", json.dumps({"calendarId": calendar_id, "text": text}))


@mcp.tool()
async def calendar_patch_event(event_id: str, calendar_id: str = "primary", summary: str = "", description: str = "", location: str = "", start_time: str = "", end_time: str = "") -> dict | str:
    """Update specific fields of a calendar event.

    Args:
        event_id: The event ID.
        calendar_id: Calendar ID.
        summary: New title.
        description: New description.
        location: New location.
        start_time: New start time (RFC3339).
        end_time: New end time (RFC3339).
    """
    body: dict = {}
    if summary:
        body["summary"] = summary
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    if start_time:
        body["start"] = {"dateTime": start_time}
    if end_time:
        body["end"] = {"dateTime": end_time}
    return await run_gws("calendar", "events", "patch", "--params", json.dumps({"calendarId": calendar_id, "eventId": event_id}), "--json", json.dumps(body))


@mcp.tool()
async def calendar_list_calendars() -> dict | str:
    """List all calendars the user has access to."""
    return await run_gws("calendar", "calendarList", "list")


@mcp.tool()
async def calendar_freebusy(time_min: str, time_max: str, calendar_ids: list[str] | None = None) -> dict | str:
    """Query free/busy information for calendars.

    Args:
        time_min: Start of window (RFC3339).
        time_max: End of window (RFC3339).
        calendar_ids: Calendar IDs to query (defaults to ['primary']).
    """
    items = [{"id": cid} for cid in (calendar_ids or ["primary"])]
    return await run_gws("calendar", "freebusy", "query", "--json", json.dumps({"timeMin": time_min, "timeMax": time_max, "items": items}))


# ========================== SHEETS ==========================


@mcp.tool()
async def sheets_read(spreadsheet_id: str, range: str) -> dict | str:
    """Read values from a spreadsheet using +read helper.

    Args:
        spreadsheet_id: The spreadsheet ID.
        range: Range to read (e.g. 'Sheet1!A1:D10').
    """
    return await run_gws("sheets", "+read", "--spreadsheet", spreadsheet_id, "--range", range)


@mcp.tool()
async def sheets_append(spreadsheet_id: str, values: str = "", json_values: str = "") -> dict | str:
    """Append rows to a spreadsheet using +append helper.

    Args:
        spreadsheet_id: The spreadsheet ID.
        values: Comma-separated values for a single row (e.g. 'Alice,100,true').
        json_values: JSON array of rows (e.g. '[["a","b"],["c","d"]]').
    """
    args = ["sheets", "+append", "--spreadsheet", spreadsheet_id]
    if json_values:
        args.extend(["--json-values", json_values])
    elif values:
        args.extend(["--values", values])
    return await run_gws(*args)


@mcp.tool()
async def sheets_get_values(spreadsheet_id: str, range: str = "Sheet1") -> dict | str:
    """Read values from a spreadsheet using raw API.

    Args:
        spreadsheet_id: The spreadsheet ID.
        range: A1 range to read.
    """
    return await run_gws("sheets", "spreadsheets", "values", "get", "--params", json.dumps({"spreadsheetId": spreadsheet_id, "range": range}))


@mcp.tool()
async def sheets_update_values(spreadsheet_id: str, range: str, values: list[list]) -> dict | str:
    """Write values to a spreadsheet.

    Args:
        spreadsheet_id: The spreadsheet ID.
        range: A1 range to write.
        values: 2D array of values.
    """
    return await run_gws("sheets", "spreadsheets", "values", "update", "--params", json.dumps({"spreadsheetId": spreadsheet_id, "range": range, "valueInputOption": "USER_ENTERED"}), "--json", json.dumps({"values": values}))


@mcp.tool()
async def sheets_create(title: str) -> dict | str:
    """Create a new spreadsheet.

    Args:
        title: Spreadsheet title.
    """
    return await run_gws("sheets", "spreadsheets", "create", "--json", json.dumps({"properties": {"title": title}}))


@mcp.tool()
async def sheets_batch_update(spreadsheet_id: str, requests: list[dict]) -> dict | str:
    """Apply batch updates to a spreadsheet (formatting, sheets, etc).

    Args:
        spreadsheet_id: The spreadsheet ID.
        requests: List of update request objects.
    """
    return await run_gws("sheets", "spreadsheets", "batchUpdate", "--params", json.dumps({"spreadsheetId": spreadsheet_id}), "--json", json.dumps({"requests": requests}))


# ========================== DOCS ==========================


@mcp.tool()
async def docs_get(document_id: str) -> dict | str:
    """Get a Google Docs document.

    Args:
        document_id: The document ID.
    """
    return await run_gws("docs", "documents", "get", "--params", json.dumps({"documentId": document_id}))


@mcp.tool()
async def docs_create(title: str) -> dict | str:
    """Create a new Google Doc.

    Args:
        title: Document title.
    """
    return await run_gws("docs", "documents", "create", "--json", json.dumps({"title": title}))


@mcp.tool()
async def docs_write(document_id: str, text: str) -> dict | str:
    """Append text to a Google Doc using +write helper.

    Args:
        document_id: The document ID.
        text: Text to append (plain text).
    """
    return await run_gws("docs", "+write", "--document", document_id, "--text", text)


@mcp.tool()
async def docs_batch_update(document_id: str, requests: list[dict]) -> dict | str:
    """Apply batch updates to a Google Doc (insert, delete, format text).

    Args:
        document_id: The document ID.
        requests: List of update request objects.
    """
    return await run_gws("docs", "documents", "batchUpdate", "--params", json.dumps({"documentId": document_id}), "--json", json.dumps({"requests": requests}))


# ========================== SLIDES ==========================


@mcp.tool()
async def slides_get(presentation_id: str) -> dict | str:
    """Get a Google Slides presentation.

    Args:
        presentation_id: The presentation ID.
    """
    return await run_gws("slides", "presentations", "get", "--params", json.dumps({"presentationId": presentation_id}))


@mcp.tool()
async def slides_create(title: str) -> dict | str:
    """Create a new presentation.

    Args:
        title: Presentation title.
    """
    return await run_gws("slides", "presentations", "create", "--json", json.dumps({"title": title}))


@mcp.tool()
async def slides_batch_update(presentation_id: str, requests: list[dict]) -> dict | str:
    """Apply batch updates to a presentation.

    Args:
        presentation_id: The presentation ID.
        requests: List of update request objects.
    """
    return await run_gws("slides", "presentations", "batchUpdate", "--params", json.dumps({"presentationId": presentation_id}), "--json", json.dumps({"requests": requests}))


# ========================== TASKS ==========================


@mcp.tool()
async def tasks_list_tasklists() -> dict | str:
    """List all Google Tasks task lists."""
    return await run_gws("tasks", "tasklists", "list")


@mcp.tool()
async def tasks_list_tasks(tasklist_id: str = "@default", show_completed: bool = True, max_results: int = 20) -> dict | str:
    """List tasks in a task list.

    Args:
        tasklist_id: The task list ID (default: '@default').
        show_completed: Include completed tasks.
        max_results: Maximum tasks to return.
    """
    return await run_gws("tasks", "tasks", "list", "--params", json.dumps({"tasklist": tasklist_id, "maxResults": max_results, "showCompleted": show_completed}))


@mcp.tool()
async def tasks_create_task(title: str, tasklist_id: str = "@default", notes: str = "", due: str = "") -> dict | str:
    """Create a new task.

    Args:
        title: Task title.
        tasklist_id: Task list ID.
        notes: Optional notes.
        due: Due date (RFC3339).
    """
    body: dict = {"title": title}
    if notes:
        body["notes"] = notes
    if due:
        body["due"] = due
    return await run_gws("tasks", "tasks", "insert", "--params", json.dumps({"tasklist": tasklist_id}), "--json", json.dumps(body))


@mcp.tool()
async def tasks_update_task(task_id: str, tasklist_id: str = "@default", title: str = "", notes: str = "", status: str = "") -> dict | str:
    """Update a task.

    Args:
        task_id: The task ID.
        tasklist_id: Task list ID.
        title: New title.
        notes: New notes.
        status: New status: 'needsAction' or 'completed'.
    """
    body: dict = {}
    if title:
        body["title"] = title
    if notes:
        body["notes"] = notes
    if status:
        body["status"] = status
    return await run_gws("tasks", "tasks", "patch", "--params", json.dumps({"tasklist": tasklist_id, "task": task_id}), "--json", json.dumps(body))


@mcp.tool()
async def tasks_delete_task(task_id: str, tasklist_id: str = "@default") -> dict | str:
    """Delete a task.

    Args:
        task_id: The task ID.
        tasklist_id: Task list ID.
    """
    return await run_gws("tasks", "tasks", "delete", "--params", json.dumps({"tasklist": tasklist_id, "task": task_id}))


@mcp.tool()
async def tasks_create_tasklist(title: str) -> dict | str:
    """Create a new task list.

    Args:
        title: Task list title.
    """
    return await run_gws("tasks", "tasklists", "insert", "--json", json.dumps({"title": title}))


@mcp.tool()
async def tasks_clear_completed(tasklist_id: str = "@default") -> dict | str:
    """Clear all completed tasks from a task list.

    Args:
        tasklist_id: Task list ID.
    """
    return await run_gws("tasks", "tasks", "clear", "--params", json.dumps({"tasklist": tasklist_id}))


# ========================== PEOPLE ==========================


@mcp.tool()
async def people_list_connections(max_results: int = 20, person_fields: str = "names,emailAddresses,phoneNumbers") -> dict | str:
    """List the user's contacts.

    Args:
        max_results: Maximum contacts to return.
        person_fields: Comma-separated fields to include.
    """
    return await run_gws("people", "people", "connections", "list", "--params", json.dumps({"resourceName": "people/me", "pageSize": max_results, "personFields": person_fields}))


@mcp.tool()
async def people_get_person(resource_name: str, person_fields: str = "names,emailAddresses,phoneNumbers,organizations") -> dict | str:
    """Get a person/contact by resource name.

    Args:
        resource_name: Person resource name (e.g. 'people/c1234567890').
        person_fields: Fields to include.
    """
    return await run_gws("people", "people", "get", "--params", json.dumps({"resourceName": resource_name, "personFields": person_fields}))


@mcp.tool()
async def people_search_contacts(query: str, max_results: int = 10) -> dict | str:
    """Search contacts by name or email.

    Args:
        query: Search query.
        max_results: Maximum results.
    """
    return await run_gws("people", "people", "searchContacts", "--params", json.dumps({"query": query, "pageSize": max_results, "readMask": "names,emailAddresses,phoneNumbers"}))


@mcp.tool()
async def people_create_contact(given_name: str, family_name: str = "", email: str = "", phone: str = "") -> dict | str:
    """Create a new contact.

    Args:
        given_name: First name.
        family_name: Last name.
        email: Email address.
        phone: Phone number.
    """
    body: dict = {"names": [{"givenName": given_name}]}
    if family_name:
        body["names"][0]["familyName"] = family_name
    if email:
        body["emailAddresses"] = [{"value": email}]
    if phone:
        body["phoneNumbers"] = [{"value": phone}]
    return await run_gws("people", "people", "createContact", "--json", json.dumps(body))


@mcp.tool()
async def people_list_contact_groups(max_results: int = 20) -> dict | str:
    """List contact groups.

    Args:
        max_results: Maximum groups to return.
    """
    return await run_gws("people", "contactGroups", "list", "--params", json.dumps({"pageSize": max_results}))


# ========================== CHAT ==========================


@mcp.tool()
async def chat_list_spaces() -> dict | str:
    """List Google Chat spaces."""
    return await run_gws("chat", "spaces", "list")


@mcp.tool()
async def chat_get_space(space_name: str) -> dict | str:
    """Get details of a Chat space.

    Args:
        space_name: Space resource name (e.g. 'spaces/AAAA1234').
    """
    return await run_gws("chat", "spaces", "get", "--params", json.dumps({"name": space_name}))


@mcp.tool()
async def chat_send(space: str, text: str) -> dict | str:
    """Send a message to a Chat space using +send helper.

    Args:
        space: Space name (e.g. spaces/AAAAxxxx).
        text: Message text.
    """
    return await run_gws("chat", "+send", "--space", space, "--text", text)


@mcp.tool()
async def chat_list_messages(space_name: str, max_results: int = 25) -> dict | str:
    """List messages in a Chat space.

    Args:
        space_name: Space resource name.
        max_results: Maximum messages.
    """
    return await run_gws("chat", "spaces", "messages", "list", "--params", json.dumps({"parent": space_name, "pageSize": max_results}))


@mcp.tool()
async def chat_create_space(display_name: str, space_type: str = "SPACE") -> dict | str:
    """Create a new Chat space.

    Args:
        display_name: Display name for the space.
        space_type: Space type: SPACE or GROUP_CHAT.
    """
    return await run_gws("chat", "spaces", "create", "--json", json.dumps({"displayName": display_name, "spaceType": space_type}))


@mcp.tool()
async def chat_list_members(space_name: str) -> dict | str:
    """List members of a Chat space.

    Args:
        space_name: Space resource name.
    """
    return await run_gws("chat", "spaces", "members", "list", "--params", json.dumps({"parent": space_name}))


# ========================== CLASSROOM ==========================


@mcp.tool()
async def classroom_list_courses(max_results: int = 20, course_states: str = "ACTIVE") -> dict | str:
    """List Google Classroom courses.

    Args:
        max_results: Maximum courses.
        course_states: Filter: ACTIVE, ARCHIVED, PROVISIONED, DECLINED, SUSPENDED.
    """
    params: dict = {"pageSize": max_results}
    if course_states:
        params["courseStates"] = course_states
    return await run_gws("classroom", "courses", "list", "--params", json.dumps(params))


@mcp.tool()
async def classroom_get_course(course_id: str) -> dict | str:
    """Get a Classroom course.

    Args:
        course_id: The course ID.
    """
    return await run_gws("classroom", "courses", "get", "--params", json.dumps({"id": course_id}))


@mcp.tool()
async def classroom_list_students(course_id: str, max_results: int = 30) -> dict | str:
    """List students in a course.

    Args:
        course_id: The course ID.
        max_results: Maximum students.
    """
    return await run_gws("classroom", "courses", "students", "list", "--params", json.dumps({"courseId": course_id, "pageSize": max_results}))


@mcp.tool()
async def classroom_list_teachers(course_id: str) -> dict | str:
    """List teachers in a course.

    Args:
        course_id: The course ID.
    """
    return await run_gws("classroom", "courses", "teachers", "list", "--params", json.dumps({"courseId": course_id}))


@mcp.tool()
async def classroom_list_coursework(course_id: str, max_results: int = 20) -> dict | str:
    """List coursework (assignments) in a course.

    Args:
        course_id: The course ID.
        max_results: Maximum items.
    """
    return await run_gws("classroom", "courses", "courseWork", "list", "--params", json.dumps({"courseId": course_id, "pageSize": max_results}))


@mcp.tool()
async def classroom_list_announcements(course_id: str, max_results: int = 20) -> dict | str:
    """List announcements in a course.

    Args:
        course_id: The course ID.
        max_results: Maximum items.
    """
    return await run_gws("classroom", "courses", "announcements", "list", "--params", json.dumps({"courseId": course_id, "pageSize": max_results}))


@mcp.tool()
async def classroom_create_course(name: str, section: str = "", description: str = "") -> dict | str:
    """Create a Classroom course.

    Args:
        name: Course name.
        section: Course section.
        description: Course description.
    """
    body: dict = {"name": name}
    if section:
        body["section"] = section
    if description:
        body["description"] = description
    return await run_gws("classroom", "courses", "create", "--json", json.dumps(body))


# ========================== FORMS ==========================


@mcp.tool()
async def forms_get(form_id: str) -> dict | str:
    """Get a Google Form by ID.

    Args:
        form_id: The form ID.
    """
    return await run_gws("forms", "forms", "get", "--params", json.dumps({"formId": form_id}))


@mcp.tool()
async def forms_create(title: str, document_title: str = "") -> dict | str:
    """Create a new Google Form.

    Args:
        title: Form title.
        document_title: Document title in Drive.
    """
    body: dict = {"info": {"title": title}}
    if document_title:
        body["info"]["documentTitle"] = document_title
    return await run_gws("forms", "forms", "create", "--json", json.dumps(body))


@mcp.tool()
async def forms_batch_update(form_id: str, requests: list[dict]) -> dict | str:
    """Apply batch updates to a form (add/remove/modify items).

    Args:
        form_id: The form ID.
        requests: List of update request objects.
    """
    return await run_gws("forms", "forms", "batchUpdate", "--params", json.dumps({"formId": form_id}), "--json", json.dumps({"requests": requests}))


@mcp.tool()
async def forms_list_responses(form_id: str, max_results: int = 50) -> dict | str:
    """List responses for a form.

    Args:
        form_id: The form ID.
        max_results: Maximum responses.
    """
    return await run_gws("forms", "forms", "responses", "list", "--params", json.dumps({"formId": form_id, "pageSize": max_results}))


# ========================== KEEP ==========================


@mcp.tool()
async def keep_list_notes(max_results: int = 20) -> dict | str:
    """List Google Keep notes.

    Args:
        max_results: Maximum notes to return.
    """
    return await run_gws("keep", "notes", "list", "--params", json.dumps({"pageSize": max_results}))


@mcp.tool()
async def keep_get_note(note_id: str) -> dict | str:
    """Get a Keep note.

    Args:
        note_id: The note ID (e.g. 'notes/abc123').
    """
    return await run_gws("keep", "notes", "get", "--params", json.dumps({"name": note_id}))


@mcp.tool()
async def keep_create_note(title: str, text_content: str = "", list_items: list[str] | None = None) -> dict | str:
    """Create a Keep note.

    Args:
        title: Note title.
        text_content: Plain text body (for text notes).
        list_items: Checklist items (for list notes, overrides text_content).
    """
    body: dict = {"title": title}
    if list_items:
        body["body"] = {"list": {"listItems": [{"text": {"text": item}} for item in list_items]}}
    elif text_content:
        body["body"] = {"text": {"text": text_content}}
    return await run_gws("keep", "notes", "create", "--json", json.dumps(body))


@mcp.tool()
async def keep_delete_note(note_id: str) -> dict | str:
    """Delete a Keep note.

    Args:
        note_id: The note ID.
    """
    return await run_gws("keep", "notes", "delete", "--params", json.dumps({"name": note_id}))


# ========================== MEET ==========================


@mcp.tool()
async def meet_create_space() -> dict | str:
    """Create a new Meet space (generates a meeting link)."""
    return await run_gws("meet", "spaces", "create", "--json", "{}")


@mcp.tool()
async def meet_get_space(space_name: str) -> dict | str:
    """Get details of a Meet space.

    Args:
        space_name: Space resource name.
    """
    return await run_gws("meet", "spaces", "get", "--params", json.dumps({"name": space_name}))


@mcp.tool()
async def meet_end_active_conference(space_name: str) -> dict | str:
    """End an active Meet conference.

    Args:
        space_name: Space resource name.
    """
    return await run_gws("meet", "spaces", "endActiveConference", "--params", json.dumps({"name": space_name}))


@mcp.tool()
async def meet_patch_space(space_name: str, config: dict | None = None) -> dict | str:
    """Update a Meet space.

    Args:
        space_name: Space resource name.
        config: Space configuration fields to update.
    """
    return await run_gws("meet", "spaces", "patch", "--params", json.dumps({"name": space_name}), "--json", json.dumps(config or {}))


@mcp.tool()
async def meet_list_conference_records(max_results: int = 10) -> dict | str:
    """List Meet conference records.

    Args:
        max_results: Maximum records.
    """
    return await run_gws("meet", "conferenceRecords", "list", "--params", json.dumps({"pageSize": max_results}))


@mcp.tool()
async def meet_list_participants(conference_record: str) -> dict | str:
    """List participants of a Meet conference.

    Args:
        conference_record: Conference record name (e.g. 'conferenceRecords/abc').
    """
    return await run_gws("meet", "conferenceRecords", "participants", "list", "--params", json.dumps({"parent": conference_record}))


@mcp.tool()
async def meet_list_recordings(conference_record: str) -> dict | str:
    """List recordings of a Meet conference.

    Args:
        conference_record: Conference record name.
    """
    return await run_gws("meet", "conferenceRecords", "recordings", "list", "--params", json.dumps({"parent": conference_record}))


# ========================== ADMIN REPORTS ==========================


@mcp.tool()
async def admin_list_activities(application_name: str = "login", user_key: str = "all", max_results: int = 25, event_name: str = "", start_time: str = "", end_time: str = "") -> dict | str:
    """Query admin audit logs.

    Args:
        application_name: App: login, admin, drive, calendar, token, groups, etc.
        user_key: User email or 'all'.
        max_results: Maximum activities.
        event_name: Filter by event (e.g. 'login_failure').
        start_time: RFC3339 start time.
        end_time: RFC3339 end time.
    """
    params: dict = {"applicationName": application_name, "userKey": user_key, "maxResults": max_results}
    if event_name:
        params["eventName"] = event_name
    if start_time:
        params["startTime"] = start_time
    if end_time:
        params["endTime"] = end_time
    return await run_gws("admin-reports", "activities", "list", "--params", json.dumps(params))


@mcp.tool()
async def admin_customer_usage_report(date: str) -> dict | str:
    """Get customer-level usage report for a date.

    Args:
        date: Date in YYYY-MM-DD format.
    """
    return await run_gws("admin-reports", "customerUsageReports", "get", "--params", json.dumps({"date": date}))


@mcp.tool()
async def admin_user_usage_report(user_key: str, date: str) -> dict | str:
    """Get user usage report.

    Args:
        user_key: User email or 'all'.
        date: Date in YYYY-MM-DD format.
    """
    return await run_gws("admin-reports", "userUsageReport", "get", "--params", json.dumps({"userKey": user_key, "date": date}))


# ========================== EVENTS ==========================


@mcp.tool()
async def events_create_subscription(target_resource: str, event_types: list[str], notification_endpoint: str) -> dict | str:
    """Create a Workspace Events subscription.

    Args:
        target_resource: Target (e.g. '//chat.googleapis.com/spaces/AAAA').
        event_types: Event types list.
        notification_endpoint: Pub/Sub topic.
    """
    return await run_gws("events", "subscriptions", "create", "--json", json.dumps({"targetResource": target_resource, "eventTypes": event_types, "notificationEndpoint": {"pubsubTopic": notification_endpoint}}))


@mcp.tool()
async def events_list_subscriptions() -> dict | str:
    """List active Workspace Events subscriptions."""
    return await run_gws("events", "subscriptions", "list")


@mcp.tool()
async def events_get_subscription(subscription_name: str) -> dict | str:
    """Get a Workspace Events subscription.

    Args:
        subscription_name: Subscription resource name.
    """
    return await run_gws("events", "subscriptions", "get", "--params", json.dumps({"name": subscription_name}))


@mcp.tool()
async def events_delete_subscription(subscription_name: str) -> dict | str:
    """Delete a Workspace Events subscription.

    Args:
        subscription_name: Subscription resource name.
    """
    return await run_gws("events", "subscriptions", "delete", "--params", json.dumps({"name": subscription_name}))


@mcp.tool()
async def events_reactivate_subscription(subscription_name: str) -> dict | str:
    """Reactivate a suspended subscription.

    Args:
        subscription_name: Subscription resource name.
    """
    return await run_gws("events", "subscriptions", "reactivate", "--params", json.dumps({"name": subscription_name}))


@mcp.tool()
async def events_subscribe(target: str = "", event_types: str = "", project: str = "", subscription: str = "", once: bool = False, cleanup: bool = False) -> dict | str:
    """Subscribe to Workspace events and stream as NDJSON using +subscribe helper.

    Args:
        target: Workspace resource URI.
        event_types: Comma-separated CloudEvents types.
        project: GCP project ID for Pub/Sub.
        subscription: Existing Pub/Sub subscription (skip setup).
        once: Pull once and exit.
        cleanup: Delete Pub/Sub resources on exit.
    """
    args = ["events", "+subscribe"]
    if subscription:
        args.extend(["--subscription", subscription])
    else:
        if target:
            args.extend(["--target", target])
        if event_types:
            args.extend(["--event-types", event_types])
        if project:
            args.extend(["--project", project])
    if once:
        args.append("--once")
    if cleanup:
        args.append("--cleanup")
    return await run_gws(*args)


@mcp.tool()
async def events_renew() -> dict | str:
    """Renew/reactivate Workspace Events subscriptions using +renew helper."""
    return await run_gws("events", "+renew")


# ========================== MODEL ARMOR ==========================


@mcp.tool()
async def modelarmor_sanitize_prompt(text: str, template: str = "") -> dict | str:
    """Sanitize a user prompt through Model Armor using +sanitize-prompt helper.

    Args:
        text: The prompt text to sanitize.
        template: Model Armor template name.
    """
    args = ["modelarmor", "+sanitize-prompt"]
    if template:
        args.extend(["--template", template])
    return await run_gws(*args, input_data=text)


@mcp.tool()
async def modelarmor_sanitize_response(text: str, template: str = "") -> dict | str:
    """Sanitize a model response through Model Armor using +sanitize-response helper.

    Args:
        text: The response text to sanitize.
        template: Model Armor template name.
    """
    args = ["modelarmor", "+sanitize-response"]
    if template:
        args.extend(["--template", template])
    return await run_gws(*args, input_data=text)


@mcp.tool()
async def modelarmor_create_template(project: str, location: str, template_id: str, config: dict | None = None) -> dict | str:
    """Create a new Model Armor template using +create-template helper.

    Args:
        project: GCP project ID.
        location: GCP location.
        template_id: Template ID to create.
        config: Template configuration (optional).
    """
    args = ["modelarmor", "+create-template", "--project", project, "--location", location, "--template-id", template_id]
    if config:
        args.extend(["--json", json.dumps(config)])
    return await run_gws(*args)


# ========================== WORKFLOW ==========================


@mcp.tool()
async def workflow_standup_report() -> dict | str:
    """Generate a standup report: today's meetings + open tasks."""
    return await run_gws("workflow", "+standup-report")


@mcp.tool()
async def workflow_meeting_prep() -> dict | str:
    """Prepare for your next meeting: agenda, attendees, and linked docs."""
    return await run_gws("workflow", "+meeting-prep")


@mcp.tool()
async def workflow_email_to_task(message_id: str = "") -> dict | str:
    """Convert a Gmail message into a Google Tasks entry.

    Args:
        message_id: Gmail message ID (optional, uses latest if empty).
    """
    args = ["workflow", "+email-to-task"]
    if message_id:
        args.extend(["--message-id", message_id])
    return await run_gws(*args)


@mcp.tool()
async def workflow_weekly_digest() -> dict | str:
    """Generate a weekly digest: this week's meetings + unread email count."""
    return await run_gws("workflow", "+weekly-digest")


@mcp.tool()
async def workflow_file_announce(file_id: str, space: str) -> dict | str:
    """Announce a Drive file in a Chat space.

    Args:
        file_id: Drive file ID.
        space: Chat space name.
    """
    return await run_gws("workflow", "+file-announce", "--file-id", file_id, "--space", space)


# ========================== GENERIC ==========================


@mcp.tool()
async def gws_raw(
    service: str,
    resource: str,
    method: str,
    params: str = "{}",
    body: str = "",
    page_all: bool = False,
    page_limit: int | None = None,
    dry_run: bool = False,
    upload: str = "",
    output: str = "",
    format: str = "",
) -> dict | str:
    """Execute any gws CLI command (for APIs not covered by specific tools).

    Use gws_schema first to discover the method's parameters.

    Args:
        service: Service name (drive, gmail, calendar, sheets, docs, slides, tasks, people, chat, classroom, forms, keep, meet, events, admin-reports, modelarmor).
        resource: Resource path, space-separated (e.g. 'files', 'users messages').
        method: Method name (e.g. 'list', 'get', 'create').
        params: JSON string of URL/query parameters.
        body: JSON string of request body.
        page_all: Auto-paginate all results.
        page_limit: Max pages when paginating.
        dry_run: Validate without calling API.
        upload: File path for multipart upload.
        output: File path to save binary response.
        format: Output format: json, table, yaml, csv.
    """
    args = [service] + resource.split() + [method, "--params", params]
    if body:
        args.extend(["--json", body])
    return await run_gws(
        *args,
        page_all=page_all,
        page_limit=page_limit,
        dry_run=dry_run,
        upload_path=upload or None,
        output_path=output or None,
        output_format=format or None,
    )


@mcp.tool()
async def gws_schema(method: str) -> dict | str:
    """Get the schema for any Google Workspace API method.

    Shows required params, types, and defaults. Use before calling gws_raw.

    Args:
        method: API method (e.g. 'drive.files.list', 'gmail.users.messages.send').
    """
    return await run_gws("schema", method)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GWS MCP Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to")
    parser.add_argument(
        "--transport",
        choices=["streamable-http", "sse", "stdio"],
        default="streamable-http",
        help="MCP transport type",
    )
    args = parser.parse_args()

    logger.info(f"Starting GWS MCP Server on {args.host}:{args.port} ({args.transport})")
    logger.info(f"gws binary: {GWS_BIN or 'NOT FOUND'}")

    asyncio.run(
        mcp.run_async(
            transport=args.transport,
            host=args.host,
            port=args.port,
        )
    )
