# GWS MCP Server

MCP Server wrapping Google Workspace CLI (`gws`) — exposes **all** Google Workspace services (Gmail, Drive, Calendar, Sheets, Docs, Slides, Tasks, People, Chat, Classroom, Forms, Keep, Meet, Admin Reports, Events, Model Armor, Workflow) as MCP tools over **Streamable HTTP** transport.

## Architecture

```
Agent (sandbox) --HTTP--> gws-mcp-server --CLI--> gws --API--> Google Workspace
```

## Prerequisites

- Python 3.10+
- Node.js 18+ (for `gws` CLI)
- `gws` CLI authenticated

## Quick Start

### 1. Install gws CLI & authenticate

```bash
npm install -g @googleworkspace/cli
gws auth setup
gws auth login -s drive,gmail,calendar,sheets,docs
```

### 2. Install Python deps

```bash
pip install fastmcp
```

### 3. Run the server

```bash
python server.py --port 8000 --transport streamable-http
```

### 4. Connect your agent

In your agent platform MCP config:

- **Transport:** Streamable HTTP
- **URL:** `http://YOUR_HOST:8000/mcp`

## Docker

```bash
# Build
docker build -t gws-mcp .

# Export credentials first (on a machine with browser)
gws auth export --unmasked > credentials.json

# Run
docker run -p 8000:8000 -v ./credentials.json:/app/credentials.json gws-mcp

```

## Available Tools

### Gmail

| Tool                   | Description                |
| ---------------------- | -------------------------- |
| `gmail_list_messages`  | Search/list Gmail messages |
| `gmail_get_message`    | Get a specific message     |
| `gmail_send_message`   | Send an email              |
| `gmail_list_labels`    | List all labels            |
| `gmail_modify_message` | Modify message labels      |

### Drive

| Tool                | Description             |
| ------------------- | ----------------------- |
| `drive_list_files`  | List/search Drive files |
| `drive_get_file`    | Get file metadata       |
| `drive_create_file` | Create a new file       |

### Calendar

| Tool                    | Description          |
| ----------------------- | -------------------- |
| `calendar_list_events`  | List upcoming events |
| `calendar_create_event` | Create an event      |
| `calendar_delete_event` | Delete an event      |

### Sheets

| Tool                   | Description              |
| ---------------------- | ------------------------ |
| `sheets_get_values`    | Read spreadsheet values  |
| `sheets_update_values` | Write spreadsheet values |
| `sheets_append_values` | Append rows              |
| `sheets_create`        | Create new spreadsheet   |

### Docs

| Tool          | Description          |
| ------------- | -------------------- |
| `docs_get`    | Get document content |
| `docs_create` | Create new document  |

### Slides

| Tool                  | Description             |
| --------------------- | ----------------------- |
| `slides_get`          | Get a presentation      |
| `slides_create`       | Create new presentation |
| `slides_batch_update` | Apply batch updates     |

### Tasks

| Tool                   | Description               |
| ---------------------- | ------------------------- |
| `tasks_list_tasklists` | List all task lists       |
| `tasks_list_tasks`     | List tasks in a task list |
| `tasks_create_task`    | Create a new task         |
| `tasks_update_task`    | Update an existing task   |
| `tasks_delete_task`    | Delete a task             |

### People (Contacts)

| Tool                      | Description           |
| ------------------------- | --------------------- |
| `people_list_connections` | List user's contacts  |
| `people_get_person`       | Get a specific person |
| `people_search_contacts`  | Search contacts       |

### Chat

| Tool                  | Description              |
| --------------------- | ------------------------ |
| `chat_list_spaces`    | List Chat spaces         |
| `chat_create_message` | Send a message           |
| `chat_list_messages`  | List messages in a space |

### Classroom

| Tool                        | Description            |
| --------------------------- | ---------------------- |
| `classroom_list_courses`    | List courses           |
| `classroom_get_course`      | Get a specific course  |
| `classroom_list_students`   | List enrolled students |
| `classroom_list_coursework` | List assignments       |

### Forms

| Tool                   | Description         |
| ---------------------- | ------------------- |
| `forms_get`            | Get a Google Form   |
| `forms_create`         | Create a new form   |
| `forms_list_responses` | List form responses |

### Keep

| Tool               | Description                       |
| ------------------ | --------------------------------- |
| `keep_list_notes`  | List notes                        |
| `keep_get_note`    | Get a specific note               |
| `keep_create_note` | Create a note (text or checklist) |

### Meet

| Tool                | Description            |
| ------------------- | ---------------------- |
| `meet_create_space` | Create a meeting space |
| `meet_get_space`    | Get meeting details    |

### Admin Reports

| Tool                    | Description      |
| ----------------------- | ---------------- |
| `admin_list_activities` | Query audit logs |

### Events

| Tool                         | Description         |
| ---------------------------- | ------------------- |
| `events_create_subscription` | Subscribe to events |
| `events_list_subscriptions`  | List subscriptions  |

### Model Armor

| Tool                  | Description              |
| --------------------- | ------------------------ |
| `modelarmor_sanitize` | Sanitize text for safety |

### Workflow

| Tool           | Description                  |
| -------------- | ---------------------------- |
| `workflow_run` | Run a cross-service workflow |

### Generic

| Tool         | Description             |
| ------------ | ----------------------- |
| `gws_raw`    | Execute any gws command |
| `gws_schema` | Get API method schema   |

## Headless Auth

If your server is headless:

```bash
# On machine with browser
gws auth login -s drive,gmail,calendar,sheets,docs
gws auth export --unmasked > credentials.json

# Transfer to server
scp credentials.json server:~/

# On server
export GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=~/credentials.json
python server.py
```

## Expose to Internet

```bash
# ngrok
ngrok http 8000

# Then use https://xxxx.ngrok.io/mcp as your MCP URL
```
