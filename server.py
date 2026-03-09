"""
MCP Server wrapping Google Workspace CLI (gws)
Exposes gws commands as MCP tools over Streamable HTTP transport.

Usage:
    # Install deps
    pip install fastmcp

    # Make sure gws is authenticated
    gws auth login -s drive,gmail,calendar,sheets,docs

    # Run server
    python server.py --port 8000

    # Then connect your agent to http://YOUR_HOST:8000/mcp
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

# ---------------------------------------------------------------------------
# Verify gws is available
# ---------------------------------------------------------------------------
GWS_BIN = shutil.which("gws")
if not GWS_BIN:
    logger.warning(
        "gws not found on PATH. Install with: npm install -g @googleworkspace/cli"
    )

# ---------------------------------------------------------------------------
# Helper: run a gws command and return parsed JSON
# ---------------------------------------------------------------------------
async def run_gws(*args: str, input_data: str | None = None) -> dict | str:
    """Execute a gws CLI command and return the result."""
    cmd = [GWS_BIN or "gws", *args]
    logger.info(f"Running: {' '.join(cmd)}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE if input_data else None,
    )

    stdout, stderr = await proc.communicate(
        input=input_data.encode() if input_data else None
    )

    output = stdout.decode().strip()
    err = stderr.decode().strip()

    if proc.returncode != 0:
        error_msg = err or output or f"gws exited with code {proc.returncode}"
        return {"error": error_msg, "returncode": proc.returncode}

    # Try to parse as JSON (gws outputs structured JSON)
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return output if output else {"message": "OK", "stderr": err}


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="gws-mcp",
    instructions=(
        "Google Workspace MCP Server wrapping the gws CLI. "
        "Provides tools for Gmail, Drive, Calendar, Sheets, Docs, and more. "
        "All responses are structured JSON from the Google Workspace APIs."
    ),
)


# ========================== GMAIL ==========================


@mcp.tool()
async def gmail_list_messages(
    query: str = "",
    max_results: int = 10,
) -> dict | str:
    """Search/list Gmail messages.

    Args:
        query: Gmail search query (e.g. 'is:unread', 'from:user@example.com', 'subject:meeting').
        max_results: Maximum number of messages to return.
    """
    params = {"maxResults": max_results, "userId": "me"}
    if query:
        params["q"] = query
    return await run_gws(
        "gmail", "users", "messages", "list",
        "--params", json.dumps(params),
    )


@mcp.tool()
async def gmail_get_message(message_id: str) -> dict | str:
    """Get a specific Gmail message by ID.

    Args:
        message_id: The Gmail message ID.
    """
    return await run_gws(
        "gmail", "users", "messages", "get",
        "--params", json.dumps({"userId": "me", "id": message_id, "format": "full"}),
    )


@mcp.tool()
async def gmail_send_message(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
) -> dict | str:
    """Send an email via Gmail.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Email body text.
        cc: CC recipients (comma-separated).
        bcc: BCC recipients (comma-separated).
    """
    import base64
    from email.mime.text import MIMEText

    msg = MIMEText(body)
    msg["to"] = to
    msg["subject"] = subject
    if cc:
        msg["cc"] = cc
    if bcc:
        msg["bcc"] = bcc

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return await run_gws(
        "gmail", "users", "messages", "send",
        "--params", json.dumps({"userId": "me"}),
        "--json", json.dumps({"raw": raw}),
    )


@mcp.tool()
async def gmail_list_labels() -> dict | str:
    """List all Gmail labels."""
    return await run_gws(
        "gmail", "users", "labels", "list",
        "--params", json.dumps({"userId": "me"}),
    )


@mcp.tool()
async def gmail_modify_message(
    message_id: str,
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
) -> dict | str:
    """Modify labels on a Gmail message (e.g. mark read/unread, archive).

    Args:
        message_id: The Gmail message ID.
        add_labels: Label IDs to add (e.g. ['STARRED', 'IMPORTANT']).
        remove_labels: Label IDs to remove (e.g. ['UNREAD', 'INBOX']).
    """
    body = {}
    if add_labels:
        body["addLabelIds"] = add_labels
    if remove_labels:
        body["removeLabelIds"] = remove_labels
    return await run_gws(
        "gmail", "users", "messages", "modify",
        "--params", json.dumps({"userId": "me", "id": message_id}),
        "--json", json.dumps(body),
    )


# ========================== DRIVE ==========================


@mcp.tool()
async def drive_list_files(
    query: str = "",
    max_results: int = 10,
    order_by: str = "modifiedTime desc",
) -> dict | str:
    """List/search files in Google Drive.

    Args:
        query: Drive search query (e.g. "name contains 'report'", "mimeType='application/pdf'").
        max_results: Maximum number of files to return.
        order_by: Sort order (default: 'modifiedTime desc').
    """
    params = {
        "pageSize": max_results,
        "orderBy": order_by,
        "fields": "files(id,name,mimeType,modifiedTime,size,webViewLink)",
    }
    if query:
        params["q"] = query
    return await run_gws("drive", "files", "list", "--params", json.dumps(params))


@mcp.tool()
async def drive_get_file(file_id: str) -> dict | str:
    """Get metadata for a specific Drive file.

    Args:
        file_id: The Google Drive file ID.
    """
    return await run_gws(
        "drive", "files", "get",
        "--params", json.dumps({
            "fileId": file_id,
            "fields": "id,name,mimeType,modifiedTime,size,webViewLink,description,owners",
        }),
    )


@mcp.tool()
async def drive_create_file(
    name: str,
    mime_type: str = "application/vnd.google-apps.document",
    parent_folder_id: str = "",
) -> dict | str:
    """Create a new file in Google Drive.

    Args:
        name: File name.
        mime_type: MIME type (e.g. 'application/vnd.google-apps.document' for Google Doc,
                   'application/vnd.google-apps.spreadsheet' for Sheet).
        parent_folder_id: Parent folder ID (optional).
    """
    body: dict = {"name": name, "mimeType": mime_type}
    if parent_folder_id:
        body["parents"] = [parent_folder_id]
    return await run_gws(
        "drive", "files", "create",
        "--json", json.dumps(body),
    )


# ========================== CALENDAR ==========================


@mcp.tool()
async def calendar_list_events(
    time_min: str = "",
    time_max: str = "",
    max_results: int = 10,
    calendar_id: str = "primary",
) -> dict | str:
    """List upcoming calendar events.

    Args:
        time_min: Start time in RFC3339 format (e.g. '2025-01-01T00:00:00Z'). Defaults to now.
        time_max: End time in RFC3339 format. Optional.
        max_results: Maximum number of events to return.
        calendar_id: Calendar ID (default 'primary').
    """
    from datetime import datetime, timezone

    params: dict = {
        "calendarId": calendar_id,
        "maxResults": max_results,
        "singleEvents": True,
        "orderBy": "startTime",
    }
    if time_min:
        params["timeMin"] = time_min
    else:
        params["timeMin"] = datetime.now(timezone.utc).isoformat()
    if time_max:
        params["timeMax"] = time_max

    return await run_gws(
        "calendar", "events", "list",
        "--params", json.dumps(params),
    )


@mcp.tool()
async def calendar_create_event(
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
    attendees: list[str] | None = None,
    calendar_id: str = "primary",
) -> dict | str:
    """Create a new calendar event.

    Args:
        summary: Event title.
        start_time: Start time in RFC3339 (e.g. '2025-03-10T09:00:00+07:00').
        end_time: End time in RFC3339.
        description: Event description.
        location: Event location.
        attendees: List of attendee email addresses.
        calendar_id: Calendar ID (default 'primary').
    """
    body: dict = {
        "summary": summary,
        "start": {"dateTime": start_time},
        "end": {"dateTime": end_time},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    if attendees:
        body["attendees"] = [{"email": e} for e in attendees]

    return await run_gws(
        "calendar", "events", "insert",
        "--params", json.dumps({"calendarId": calendar_id}),
        "--json", json.dumps(body),
    )


@mcp.tool()
async def calendar_delete_event(
    event_id: str,
    calendar_id: str = "primary",
) -> dict | str:
    """Delete a calendar event.

    Args:
        event_id: The event ID to delete.
        calendar_id: Calendar ID (default 'primary').
    """
    return await run_gws(
        "calendar", "events", "delete",
        "--params", json.dumps({
            "calendarId": calendar_id,
            "eventId": event_id,
        }),
    )


# ========================== SHEETS ==========================


@mcp.tool()
async def sheets_get_values(
    spreadsheet_id: str,
    range: str = "Sheet1",
) -> dict | str:
    """Read values from a Google Sheets spreadsheet.

    Args:
        spreadsheet_id: The spreadsheet ID.
        range: The A1 range to read (e.g. 'Sheet1!A1:C10').
    """
    return await run_gws(
        "sheets", "spreadsheets", "values", "get",
        "--params", json.dumps({
            "spreadsheetId": spreadsheet_id,
            "range": range,
        }),
    )


@mcp.tool()
async def sheets_update_values(
    spreadsheet_id: str,
    range: str,
    values: list[list],
) -> dict | str:
    """Write values to a Google Sheets spreadsheet.

    Args:
        spreadsheet_id: The spreadsheet ID.
        range: The A1 range to write (e.g. 'Sheet1!A1').
        values: 2D array of values to write (e.g. [['Name', 'Score'], ['Alice', 95]]).
    """
    return await run_gws(
        "sheets", "spreadsheets", "values", "update",
        "--params", json.dumps({
            "spreadsheetId": spreadsheet_id,
            "range": range,
            "valueInputOption": "USER_ENTERED",
        }),
        "--json", json.dumps({"values": values}),
    )


@mcp.tool()
async def sheets_append_values(
    spreadsheet_id: str,
    range: str,
    values: list[list],
) -> dict | str:
    """Append rows to a Google Sheets spreadsheet.

    Args:
        spreadsheet_id: The spreadsheet ID.
        range: The A1 range to append to (e.g. 'Sheet1!A1').
        values: 2D array of values to append.
    """
    return await run_gws(
        "sheets", "spreadsheets", "values", "append",
        "--params", json.dumps({
            "spreadsheetId": spreadsheet_id,
            "range": range,
            "valueInputOption": "USER_ENTERED",
        }),
        "--json", json.dumps({"values": values}),
    )


@mcp.tool()
async def sheets_create(title: str) -> dict | str:
    """Create a new Google Sheets spreadsheet.

    Args:
        title: Title for the new spreadsheet.
    """
    return await run_gws(
        "sheets", "spreadsheets", "create",
        "--json", json.dumps({"properties": {"title": title}}),
    )


# ========================== DOCS ==========================


@mcp.tool()
async def docs_get(document_id: str) -> dict | str:
    """Get a Google Docs document content.

    Args:
        document_id: The document ID.
    """
    return await run_gws(
        "docs", "documents", "get",
        "--params", json.dumps({"documentId": document_id}),
    )


@mcp.tool()
async def docs_create(title: str) -> dict | str:
    """Create a new Google Docs document.

    Args:
        title: Title for the new document.
    """
    return await run_gws(
        "docs", "documents", "create",
        "--json", json.dumps({"title": title}),
    )


# ========================== SLIDES ==========================


@mcp.tool()
async def slides_get(presentation_id: str) -> dict | str:
    """Get a Google Slides presentation.

    Args:
        presentation_id: The presentation ID.
    """
    return await run_gws(
        "slides", "presentations", "get",
        "--params", json.dumps({"presentationId": presentation_id}),
    )


@mcp.tool()
async def slides_create(title: str) -> dict | str:
    """Create a new Google Slides presentation.

    Args:
        title: Title for the new presentation.
    """
    return await run_gws(
        "slides", "presentations", "create",
        "--json", json.dumps({"title": title}),
    )


@mcp.tool()
async def slides_batch_update(
    presentation_id: str,
    requests: list[dict],
) -> dict | str:
    """Apply batch updates to a Google Slides presentation.

    Args:
        presentation_id: The presentation ID.
        requests: List of update request objects (see Slides API docs).
    """
    return await run_gws(
        "slides", "presentations", "batchUpdate",
        "--params", json.dumps({"presentationId": presentation_id}),
        "--json", json.dumps({"requests": requests}),
    )


# ========================== TASKS ==========================


@mcp.tool()
async def tasks_list_tasklists() -> dict | str:
    """List all Google Tasks task lists."""
    return await run_gws("tasks", "tasklists", "list")


@mcp.tool()
async def tasks_list_tasks(
    tasklist_id: str = "@default",
    show_completed: bool = True,
    max_results: int = 20,
) -> dict | str:
    """List tasks in a task list.

    Args:
        tasklist_id: The task list ID (default: '@default').
        show_completed: Whether to include completed tasks.
        max_results: Maximum number of tasks to return.
    """
    params: dict = {
        "tasklist": tasklist_id,
        "maxResults": max_results,
        "showCompleted": show_completed,
    }
    return await run_gws(
        "tasks", "tasks", "list",
        "--params", json.dumps(params),
    )


@mcp.tool()
async def tasks_create_task(
    title: str,
    tasklist_id: str = "@default",
    notes: str = "",
    due: str = "",
) -> dict | str:
    """Create a new task.

    Args:
        title: Task title.
        tasklist_id: The task list ID (default: '@default').
        notes: Optional notes/description.
        due: Optional due date in RFC3339 format.
    """
    body: dict = {"title": title}
    if notes:
        body["notes"] = notes
    if due:
        body["due"] = due
    return await run_gws(
        "tasks", "tasks", "insert",
        "--params", json.dumps({"tasklist": tasklist_id}),
        "--json", json.dumps(body),
    )


@mcp.tool()
async def tasks_update_task(
    task_id: str,
    tasklist_id: str = "@default",
    title: str = "",
    notes: str = "",
    status: str = "",
) -> dict | str:
    """Update an existing task.

    Args:
        task_id: The task ID.
        tasklist_id: The task list ID (default: '@default').
        title: New title (leave empty to keep unchanged).
        notes: New notes (leave empty to keep unchanged).
        status: New status: 'needsAction' or 'completed'.
    """
    body: dict = {}
    if title:
        body["title"] = title
    if notes:
        body["notes"] = notes
    if status:
        body["status"] = status
    return await run_gws(
        "tasks", "tasks", "patch",
        "--params", json.dumps({"tasklist": tasklist_id, "task": task_id}),
        "--json", json.dumps(body),
    )


@mcp.tool()
async def tasks_delete_task(
    task_id: str,
    tasklist_id: str = "@default",
) -> dict | str:
    """Delete a task.

    Args:
        task_id: The task ID.
        tasklist_id: The task list ID (default: '@default').
    """
    return await run_gws(
        "tasks", "tasks", "delete",
        "--params", json.dumps({"tasklist": tasklist_id, "task": task_id}),
    )


# ========================== PEOPLE ==========================


@mcp.tool()
async def people_list_connections(
    max_results: int = 20,
    person_fields: str = "names,emailAddresses,phoneNumbers",
) -> dict | str:
    """List the authenticated user's contacts.

    Args:
        max_results: Maximum number of contacts to return.
        person_fields: Comma-separated person fields to include.
    """
    return await run_gws(
        "people", "people", "connections", "list",
        "--params", json.dumps({
            "resourceName": "people/me",
            "pageSize": max_results,
            "personFields": person_fields,
        }),
    )


@mcp.tool()
async def people_get_person(
    resource_name: str,
    person_fields: str = "names,emailAddresses,phoneNumbers,organizations",
) -> dict | str:
    """Get a specific person/contact by resource name.

    Args:
        resource_name: The person resource name (e.g. 'people/c1234567890').
        person_fields: Comma-separated person fields to include.
    """
    return await run_gws(
        "people", "people", "get",
        "--params", json.dumps({
            "resourceName": resource_name,
            "personFields": person_fields,
        }),
    )


@mcp.tool()
async def people_search_contacts(
    query: str,
    max_results: int = 10,
) -> dict | str:
    """Search contacts by name or email.

    Args:
        query: Search query string.
        max_results: Maximum results to return.
    """
    return await run_gws(
        "people", "people", "searchContacts",
        "--params", json.dumps({
            "query": query,
            "pageSize": max_results,
            "readMask": "names,emailAddresses,phoneNumbers",
        }),
    )


# ========================== CHAT ==========================


@mcp.tool()
async def chat_list_spaces() -> dict | str:
    """List Google Chat spaces the user is a member of."""
    return await run_gws("chat", "spaces", "list")


@mcp.tool()
async def chat_create_message(
    space_name: str,
    text: str,
) -> dict | str:
    """Send a message to a Google Chat space.

    Args:
        space_name: The space resource name (e.g. 'spaces/AAAA1234').
        text: Message text to send.
    """
    return await run_gws(
        "chat", "spaces", "messages", "create",
        "--params", json.dumps({"parent": space_name}),
        "--json", json.dumps({"text": text}),
    )


@mcp.tool()
async def chat_list_messages(
    space_name: str,
    max_results: int = 25,
) -> dict | str:
    """List messages in a Google Chat space.

    Args:
        space_name: The space resource name (e.g. 'spaces/AAAA1234').
        max_results: Maximum messages to return.
    """
    return await run_gws(
        "chat", "spaces", "messages", "list",
        "--params", json.dumps({
            "parent": space_name,
            "pageSize": max_results,
        }),
    )


# ========================== CLASSROOM ==========================


@mcp.tool()
async def classroom_list_courses(
    max_results: int = 20,
    course_states: str = "ACTIVE",
) -> dict | str:
    """List Google Classroom courses.

    Args:
        max_results: Maximum courses to return.
        course_states: Filter by state: ACTIVE, ARCHIVED, PROVISIONED, DECLINED, SUSPENDED.
    """
    params: dict = {"pageSize": max_results}
    if course_states:
        params["courseStates"] = course_states
    return await run_gws(
        "classroom", "courses", "list",
        "--params", json.dumps(params),
    )


@mcp.tool()
async def classroom_get_course(course_id: str) -> dict | str:
    """Get a specific Classroom course.

    Args:
        course_id: The course ID.
    """
    return await run_gws(
        "classroom", "courses", "get",
        "--params", json.dumps({"id": course_id}),
    )


@mcp.tool()
async def classroom_list_students(
    course_id: str,
    max_results: int = 30,
) -> dict | str:
    """List students enrolled in a course.

    Args:
        course_id: The course ID.
        max_results: Maximum students to return.
    """
    return await run_gws(
        "classroom", "courses", "students", "list",
        "--params", json.dumps({
            "courseId": course_id,
            "pageSize": max_results,
        }),
    )


@mcp.tool()
async def classroom_list_coursework(
    course_id: str,
    max_results: int = 20,
) -> dict | str:
    """List coursework (assignments) in a course.

    Args:
        course_id: The course ID.
        max_results: Maximum items to return.
    """
    return await run_gws(
        "classroom", "courses", "courseWork", "list",
        "--params", json.dumps({
            "courseId": course_id,
            "pageSize": max_results,
        }),
    )


# ========================== FORMS ==========================


@mcp.tool()
async def forms_get(form_id: str) -> dict | str:
    """Get a Google Form by ID.

    Args:
        form_id: The form ID.
    """
    return await run_gws(
        "forms", "forms", "get",
        "--params", json.dumps({"formId": form_id}),
    )


@mcp.tool()
async def forms_create(
    title: str,
    document_title: str = "",
) -> dict | str:
    """Create a new Google Form.

    Args:
        title: Form title shown to respondents.
        document_title: Document title in Drive (defaults to form title).
    """
    body: dict = {"info": {"title": title}}
    if document_title:
        body["info"]["documentTitle"] = document_title
    return await run_gws(
        "forms", "forms", "create",
        "--json", json.dumps(body),
    )


@mcp.tool()
async def forms_list_responses(
    form_id: str,
    max_results: int = 50,
) -> dict | str:
    """List responses for a Google Form.

    Args:
        form_id: The form ID.
        max_results: Maximum responses to return.
    """
    return await run_gws(
        "forms", "forms", "responses", "list",
        "--params", json.dumps({
            "formId": form_id,
            "pageSize": max_results,
        }),
    )


# ========================== KEEP ==========================


@mcp.tool()
async def keep_list_notes(
    max_results: int = 20,
) -> dict | str:
    """List Google Keep notes.

    Args:
        max_results: Maximum notes to return.
    """
    return await run_gws(
        "keep", "notes", "list",
        "--params", json.dumps({"pageSize": max_results}),
    )


@mcp.tool()
async def keep_get_note(note_id: str) -> dict | str:
    """Get a specific Google Keep note.

    Args:
        note_id: The note ID (e.g. 'notes/abc123').
    """
    return await run_gws(
        "keep", "notes", "get",
        "--params", json.dumps({"name": note_id}),
    )


@mcp.tool()
async def keep_create_note(
    title: str,
    text_content: str = "",
    list_items: list[str] | None = None,
) -> dict | str:
    """Create a new Google Keep note.

    Args:
        title: Note title.
        text_content: Plain text body (for text notes).
        list_items: List of checklist items (for list notes). Overrides text_content.
    """
    body: dict = {"title": title}
    if list_items:
        body["body"] = {
            "list": {
                "listItems": [
                    {"text": {"text": item}} for item in list_items
                ]
            }
        }
    elif text_content:
        body["body"] = {"text": {"text": text_content}}
    return await run_gws(
        "keep", "notes", "create",
        "--json", json.dumps(body),
    )


# ========================== MEET ==========================


@mcp.tool()
async def meet_create_space() -> dict | str:
    """Create a new Google Meet meeting space (generates a meeting link)."""
    return await run_gws(
        "meet", "spaces", "create",
        "--json", "{}",
    )


@mcp.tool()
async def meet_get_space(space_name: str) -> dict | str:
    """Get details of a Google Meet space.

    Args:
        space_name: The space resource name (e.g. 'spaces/abc-defg-hij').
    """
    return await run_gws(
        "meet", "spaces", "get",
        "--params", json.dumps({"name": space_name}),
    )


# ========================== ADMIN REPORTS ==========================


@mcp.tool()
async def admin_list_activities(
    application_name: str = "login",
    user_key: str = "all",
    max_results: int = 25,
    event_name: str = "",
    start_time: str = "",
    end_time: str = "",
) -> dict | str:
    """Query Google Workspace admin audit logs.

    Args:
        application_name: App to query: login, admin, drive, calendar, token, groups, etc.
        user_key: User email or 'all' for all users.
        max_results: Maximum activities to return.
        event_name: Filter by specific event (e.g. 'login_failure').
        start_time: Start time in RFC3339 format.
        end_time: End time in RFC3339 format.
    """
    params: dict = {
        "applicationName": application_name,
        "userKey": user_key,
        "maxResults": max_results,
    }
    if event_name:
        params["eventName"] = event_name
    if start_time:
        params["startTime"] = start_time
    if end_time:
        params["endTime"] = end_time
    return await run_gws(
        "admin-reports", "activities", "list",
        "--params", json.dumps(params),
    )


# ========================== EVENTS ==========================


@mcp.tool()
async def events_create_subscription(
    target_resource: str,
    event_types: list[str],
    notification_endpoint: str,
) -> dict | str:
    """Create a Google Workspace Events subscription.

    Args:
        target_resource: Target to watch (e.g. '//chat.googleapis.com/spaces/AAAA').
        event_types: Event types to subscribe to (e.g. ['google.workspace.chat.message.v1.created']).
        notification_endpoint: Cloud Pub/Sub topic for notifications.
    """
    return await run_gws(
        "events", "subscriptions", "create",
        "--json", json.dumps({
            "targetResource": target_resource,
            "eventTypes": event_types,
            "notificationEndpoint": {"pubsubTopic": notification_endpoint},
        }),
    )


@mcp.tool()
async def events_list_subscriptions() -> dict | str:
    """List active Google Workspace Events subscriptions."""
    return await run_gws("events", "subscriptions", "list")


# ========================== MODEL ARMOR ==========================


@mcp.tool()
async def modelarmor_sanitize(
    text: str,
    template: str = "",
) -> dict | str:
    """Sanitize text through Google Model Armor for content safety.

    Args:
        text: The text content to sanitize.
        template: Model Armor template name (optional, uses env default).
    """
    args = ["modelarmor", "sanitize"]
    if template:
        args.extend(["--params", json.dumps({"template": template})])
    return await run_gws(*args, input_data=text)


# ========================== WORKFLOW ==========================


@mcp.tool()
async def workflow_run(
    workflow_name: str,
    params: str = "{}",
) -> dict | str:
    """Run a cross-service gws productivity workflow.

    Args:
        workflow_name: Name of the workflow to execute.
        params: JSON string of workflow parameters.
    """
    return await run_gws(
        "workflow", "run", workflow_name,
        "--params", params,
    )


# ========================== GENERIC ==========================


@mcp.tool()
async def gws_raw(
    service: str,
    resource: str,
    method: str,
    params: str = "{}",
    body: str = "",
) -> dict | str:
    """Execute any gws CLI command (for APIs not covered by specific tools).

    Args:
        service: The Google API service (e.g. 'drive', 'gmail', 'calendar', 'tasks', 'chat').
        resource: The resource path, space-separated (e.g. 'files', 'users messages', 'events').
        method: The method (e.g. 'list', 'get', 'create', 'update', 'delete').
        params: JSON string of URL parameters.
        body: JSON string of request body (optional).
    """
    args = [service] + resource.split() + [method, "--params", params]
    if body:
        args.extend(["--json", body])
    return await run_gws(*args)


@mcp.tool()
async def gws_schema(method: str) -> dict | str:
    """Get the schema for any Google Workspace API method.

    Args:
        method: The API method (e.g. 'drive.files.list', 'gmail.users.messages.send').
    """
    return await run_gws("schema", method)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GWS MCP Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind to")
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
