"""Ground Control - Task Management for Home Assistant."""

import os
import json
import asyncio
import logging
from pathlib import Path
from typing import Set
from datetime import date

from aiohttp import web, WSMsgType

from models import Task, Project, TaskState, BUCKETS, VALID_TRANSITIONS
from parser import load_task_state, parse_buckets_file
from writer import (
    write_buckets_file,
    create_task,
    move_task,
    complete_task,
    delete_task,
    create_project,
    update_project,
    archive_project,
)
from watcher import TasksWatcher
from mqtt_client import MQTTTaskClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Possible config paths (HA maps differently in some setups)
# /homeassistant is more common in HA OS, check it first
CONFIG_PATHS = [
    "/homeassistant",
    "/config",
    "/share",
]

VERSION = "0.1.12"

# Global state
state: TaskState = TaskState()
websocket_clients: Set[web.WebSocketResponse] = set()
watcher: TasksWatcher = None
mqtt_client: MQTTTaskClient = None
tasks_path: str = "/config/.tasks"


def find_tasks_path() -> str:
    """Auto-detect the correct .tasks path."""
    for base in CONFIG_PATHS:
        candidate = Path(base) / ".tasks"
        buckets_file = candidate / "buckets.md"

        # Check that buckets.md exists AND has real content (>100 bytes)
        if candidate.exists() and buckets_file.exists():
            try:
                size = buckets_file.stat().st_size
                if size > 100:  # Real buckets.md has frontmatter + content
                    logger.info(f"Found valid .tasks at: {candidate} (buckets.md: {size} bytes)")
                    return str(candidate)
                else:
                    logger.warning(f"Skipping {candidate}: buckets.md too small ({size} bytes)")
            except Exception as e:
                logger.warning(f"Error checking {buckets_file}: {e}")

    # Log what we tried
    for base in CONFIG_PATHS:
        candidate = Path(base) / ".tasks"
        logger.warning(f"Checked {candidate}: exists={candidate.exists()}")
        if candidate.exists():
            try:
                contents = list(candidate.iterdir())
                logger.warning(f"  Contents: {contents}")
            except Exception as e:
                logger.warning(f"  Error listing: {e}")

    # Default fallback
    logger.error("Could not find valid .tasks directory!")
    return "/homeassistant/.tasks"


def load_options() -> dict:
    """Load addon options from Home Assistant."""
    options_path = "/data/options.json"
    if Path(options_path).exists():
        with open(options_path) as f:
            return json.load(f)
    return {"tasks_path": "/config/.tasks"}


async def broadcast(message: dict):
    """Broadcast message to all connected WebSocket clients."""
    if not websocket_clients:
        return

    data = json.dumps(message)
    disconnected = set()

    for ws in websocket_clients:
        try:
            await ws.send_str(data)
        except Exception:
            disconnected.add(ws)

    # Clean up disconnected clients
    websocket_clients.difference_update(disconnected)


async def reload_state():
    """Reload task state from files and broadcast update."""
    global state
    try:
        state = load_task_state(tasks_path)
        # Log counts for debugging
        counts = {b: len(tasks) for b, tasks in state.buckets.tasks.items()}
        logger.info(f"[RELOAD] Task state reloaded from {tasks_path}")
        logger.info(f"[RELOAD] Task counts: {counts}")
        logger.info(f"[RELOAD] Projects: {list(state.projects.keys())}")
        await broadcast({"type": "state", "data": state.to_dict()})
    except Exception as e:
        logger.error(f"[RELOAD] Error reloading state: {e}")


def save_buckets():
    """Save buckets to file."""
    buckets_path = Path(tasks_path) / "buckets.md"
    write_buckets_file(str(buckets_path), state.buckets)
    logger.info("Buckets saved")


# --- HTTP Routes ---


async def index_handler(request: web.Request) -> web.Response:
    """Serve the frontend HTML."""
    html_path = Path("/frontend/index.html")
    logger.info(f"index_handler: Checking {html_path}, exists={html_path.exists()}")

    if html_path.exists():
        logger.info(f"index_handler: Serving {html_path} ({html_path.stat().st_size} bytes)")
        return web.FileResponse(html_path)

    # Debug: List what's in /frontend
    frontend_dir = Path("/frontend")
    if frontend_dir.exists():
        contents = list(frontend_dir.rglob("*"))
        logger.warning(f"index_handler: /frontend exists but index.html not found. Contents: {contents}")
    else:
        logger.error(f"index_handler: /frontend directory does not exist!")
        # Check what directories exist at root
        root_contents = [p.name for p in Path("/").iterdir()]
        logger.error(f"index_handler: Root contents: {root_contents}")

    return web.Response(text="Ground Control - Frontend not found. Check addon logs.", content_type="text/html")


async def static_handler(request: web.Request) -> web.Response:
    """Serve static files (JS, CSS)."""
    filename = request.match_info.get("filename", "")
    file_path = Path("/frontend") / filename

    if file_path.exists() and file_path.is_file():
        return web.FileResponse(file_path)

    return web.Response(status=404, text="Not found")


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """WebSocket handler for real-time updates."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    websocket_clients.add(ws)
    logger.info(f"WebSocket client connected ({len(websocket_clients)} total)")

    # Send current state
    await ws.send_str(json.dumps({"type": "state", "data": state.to_dict()}))

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    await handle_ws_message(ws, data)
                except json.JSONDecodeError:
                    pass
            elif msg.type == WSMsgType.ERROR:
                logger.error(f"WebSocket error: {ws.exception()}")
    finally:
        websocket_clients.discard(ws)
        logger.info(f"WebSocket client disconnected ({len(websocket_clients)} total)")

    return ws


async def handle_ws_message(ws: web.WebSocketResponse, data: dict):
    """Handle incoming WebSocket messages."""
    msg_type = data.get("type")

    if msg_type == "refresh":
        await reload_state()


# --- API Routes ---


async def api_get_version(request: web.Request) -> web.Response:
    """Get addon version."""
    return web.json_response({"version": VERSION, "tasks_path": tasks_path})


async def api_get_tasks(request: web.Request) -> web.Response:
    """Get all tasks organized by bucket."""
    return web.json_response(state.to_dict())


async def api_get_projects(request: web.Request) -> web.Response:
    """Get all projects."""
    projects = {slug: p.to_dict() for slug, p in state.projects.items()}
    return web.json_response(projects)


async def api_get_stats(request: web.Request) -> web.Response:
    """Get computed statistics for HA sensors."""
    logger.info("[API] /api/stats called")
    buckets = state.buckets

    # Count tasks per bucket
    active_count = len(buckets.tasks.get("active", []))
    work_queue_count = len(buckets.tasks.get("work_queue", []))
    completed_count = len(buckets.tasks.get("completed", []))

    # Total open = all non-completed tasks
    total_open = sum(
        len(tasks) for bucket, tasks in buckets.tasks.items()
        if bucket != "completed"
    )

    # Count blocked tasks
    blocked_count = sum(
        1 for task in buckets.get_all_tasks()
        if task.is_blocked()
    )

    # Project stats
    project_stats = {}
    for slug, project in state.projects.items():
        # Count tasks for this project
        project_tasks = [t for t in buckets.get_all_tasks() if t.project == slug]
        open_tasks = len([t for t in project_tasks if t.bucket != "completed"])
        completed_tasks = len([t for t in project_tasks if t.bucket == "completed"])
        total = open_tasks + completed_tasks
        progress = int((completed_tasks / total * 100)) if total > 0 else 0

        project_stats[slug] = {
            "status": project.status,
            "open_tasks": open_tasks,
            "completed_tasks": completed_tasks,
            "progress": progress,
        }

    return web.json_response({
        "version": VERSION,
        "tasks_path": tasks_path,
        "active_count": active_count,
        "work_queue_count": work_queue_count,
        "total_open": total_open,
        "completed_count": completed_count,
        "blocked_count": blocked_count,
        "has_active": active_count > 0,
        "has_blocked": blocked_count > 0,
        "projects": project_stats,
    })


async def api_create_task(request: web.Request) -> web.Response:
    """Create a new task."""
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    subject = data.get("subject", "").strip()
    if not subject:
        return web.json_response({"error": "Subject is required"}, status=400)

    bucket = data.get("bucket", "brainstorm")
    if bucket not in BUCKETS:
        return web.json_response({"error": f"Invalid bucket: {bucket}"}, status=400)

    task = create_task(
        state.buckets,
        subject=subject,
        bucket=bucket,
        project=data.get("project", ""),
        description=data.get("description", ""),
    )

    save_buckets()
    await broadcast({"type": "task_created", "data": task.to_dict()})

    return web.json_response(task.to_dict(), status=201)


async def api_update_task(request: web.Request) -> web.Response:
    """Update an existing task."""
    task_id = request.match_info.get("id", "").upper()

    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    task = state.buckets.get_task_by_id(task_id)
    if not task:
        return web.json_response({"error": "Task not found"}, status=404)

    # Update fields
    if "subject" in data:
        task.subject = data["subject"]
    if "description" in data:
        task.description = data["description"]
    if "project" in data:
        task.project = data["project"]
    if "blocked_by" in data:
        task.blocked_by = data["blocked_by"]

    save_buckets()
    await broadcast({"type": "task_updated", "data": task.to_dict()})

    return web.json_response(task.to_dict())


async def api_move_task(request: web.Request) -> web.Response:
    """Move a task to a different bucket."""
    task_id = request.match_info.get("id", "").upper()

    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    target_bucket = data.get("bucket", "")
    if target_bucket not in BUCKETS:
        return web.json_response({"error": f"Invalid bucket: {target_bucket}"}, status=400)

    task = state.buckets.get_task_by_id(task_id)
    if not task:
        return web.json_response({"error": "Task not found"}, status=404)

    # Check if move is valid
    if not task.can_move_to(target_bucket):
        allowed = VALID_TRANSITIONS.get(task.bucket, [])
        return web.json_response(
            {"error": f"Cannot move from {task.bucket} to {target_bucket}. Allowed: {allowed}"},
            status=400,
        )

    # Check blocked status
    if target_bucket in ("work_queue", "active") and task.is_blocked():
        return web.json_response(
            {"error": f"Task is blocked by: {', '.join(task.blocked_by)}"},
            status=400,
        )

    success = move_task(state.buckets, task_id, target_bucket)
    if not success:
        return web.json_response({"error": "Move failed"}, status=500)

    save_buckets()
    await broadcast({"type": "task_moved", "data": task.to_dict()})

    return web.json_response(task.to_dict())


async def api_complete_task(request: web.Request) -> web.Response:
    """Mark a task as completed."""
    task_id = request.match_info.get("id", "").upper()

    task = state.buckets.get_task_by_id(task_id)
    if not task:
        return web.json_response({"error": "Task not found"}, status=404)

    # Can only complete from active
    if task.bucket != "active":
        return web.json_response(
            {"error": "Can only complete tasks from Active bucket"},
            status=400,
        )

    success = complete_task(state.buckets, task_id)
    if not success:
        return web.json_response({"error": "Complete failed"}, status=500)

    save_buckets()
    await broadcast({"type": "task_completed", "data": task.to_dict()})

    return web.json_response(task.to_dict())


async def api_delete_task(request: web.Request) -> web.Response:
    """Delete a task."""
    task_id = request.match_info.get("id", "").upper()

    success = delete_task(state.buckets, task_id)
    if not success:
        return web.json_response({"error": "Task not found"}, status=404)

    save_buckets()
    await broadcast({"type": "task_deleted", "data": {"id": task_id}})

    return web.json_response({"success": True})


# --- Project API Routes ---


async def api_create_project(request: web.Request) -> web.Response:
    """Create a new project."""
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    name = data.get("name", "").strip()
    if not name:
        return web.json_response({"error": "Name is required"}, status=400)

    goal = data.get("goal", "").strip()
    if not goal:
        return web.json_response({"error": "Goal is required"}, status=400)

    description = data.get("description", "")

    project = create_project(tasks_path, name, goal, description)

    # Reload state to pick up the new project
    await reload_state()
    await broadcast({"type": "project_created", "data": project.to_dict()})

    return web.json_response(project.to_dict(), status=201)


async def api_update_project(request: web.Request) -> web.Response:
    """Update an existing project."""
    slug = request.match_info.get("slug", "")

    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    project = update_project(
        tasks_path,
        slug,
        status=data.get("status"),
        goal=data.get("goal"),
        name=data.get("name"),
    )

    if not project:
        return web.json_response({"error": "Project not found"}, status=404)

    # Reload state to pick up the changes
    await reload_state()
    await broadcast({"type": "project_updated", "data": project.to_dict()})

    return web.json_response(project.to_dict())


async def api_archive_project(request: web.Request) -> web.Response:
    """Archive a project."""
    slug = request.match_info.get("slug", "")

    success = archive_project(tasks_path, slug)
    if not success:
        return web.json_response({"error": "Project not found"}, status=404)

    # Reload state
    await reload_state()
    await broadcast({"type": "project_archived", "data": {"slug": slug}})

    return web.json_response({"success": True})


# --- Agent Tasks API Routes ---


async def api_get_agent_tasks(request: web.Request) -> web.Response:
    """Get pending agent tasks."""
    if not mqtt_client:
        return web.json_response({"pending": [], "completed": [], "status": {"connected": False}})
    return web.json_response({
        "pending": mqtt_client.get_pending_tasks(),
        "completed": mqtt_client.get_completed_tasks(),
        "status": mqtt_client.get_status(),
    })


async def api_approve_task(request: web.Request) -> web.Response:
    """Approve an agent task and assign to bucket."""
    task_id = request.match_info.get("id", "")
    if not mqtt_client:
        return web.json_response({"error": "MQTT not connected"}, status=503)

    # Get bucket from request body
    try:
        data = await request.json()
        bucket = data.get("bucket", "work_queue")
    except:
        bucket = "work_queue"

    # Validate bucket
    if bucket not in BUCKETS:
        return web.json_response({"error": f"Invalid bucket: {bucket}"}, status=400)

    # Approve the task via MQTT
    agent_task = mqtt_client.approve_task(task_id, bucket=bucket)
    if not agent_task:
        return web.json_response({"error": "Task not found"}, status=404)

    # Create a new task in the task system
    task = create_task(
        state.buckets,
        subject=agent_task.title,
        bucket=bucket,
        description=agent_task.description,
    )

    save_buckets()
    await broadcast({"type": "agent_task_updated"})
    await broadcast({"type": "task_created", "data": task.to_dict()})

    return web.json_response({"status": "approved", "bucket": bucket, "task_id": task.id})


async def api_reject_task(request: web.Request) -> web.Response:
    """Reject an agent task."""
    task_id = request.match_info.get("id", "")
    if not mqtt_client:
        return web.json_response({"error": "MQTT not connected"}, status=503)

    try:
        data = await request.json()
        reason = data.get("reason", "")
    except:
        reason = ""

    success = mqtt_client.reject_task(task_id, reason=reason)
    if success:
        await broadcast({"type": "agent_task_updated"})
        return web.json_response({"success": True, "task_id": task_id})
    return web.json_response({"error": "Task not found"}, status=404)


async def api_get_agent_level_tasks(request: web.Request) -> web.Response:
    """Get agent-level tasks (Major Tom queue)."""
    if not mqtt_client:
        return web.json_response([])
    tasks = mqtt_client.get_agent_tasks()
    return web.json_response(tasks)


async def api_add_task_note(request: web.Request) -> web.Response:
    """Add a note to an agent-level task."""
    task_id = request.match_info.get("id", "")
    if not mqtt_client:
        return web.json_response({"error": "MQTT not connected"}, status=503)

    try:
        data = await request.json()
        note = data.get("note", "")
    except:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    if mqtt_client.add_note_to_task(task_id, note):
        await broadcast({"type": "agent_task_updated"})
        return web.json_response({"status": "ok"})
    return web.json_response({"error": "Task not found"}, status=404)


# --- Application Setup ---


def create_app() -> web.Application:
    """Create the aiohttp application."""
    app = web.Application()

    # Routes
    app.router.add_get("/", index_handler)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_static("/js", "/frontend/js")
    app.router.add_static("/css", "/frontend/css")

    # API routes
    app.router.add_get("/api/version", api_get_version)
    app.router.add_get("/api/tasks", api_get_tasks)
    app.router.add_get("/api/projects", api_get_projects)
    app.router.add_get("/api/stats", api_get_stats)
    app.router.add_post("/api/tasks", api_create_task)
    app.router.add_put("/api/tasks/{id}", api_update_task)
    app.router.add_post("/api/tasks/{id}/move", api_move_task)
    app.router.add_post("/api/tasks/{id}/complete", api_complete_task)
    app.router.add_delete("/api/tasks/{id}", api_delete_task)

    # Project routes
    app.router.add_post("/api/projects", api_create_project)
    app.router.add_put("/api/projects/{slug}", api_update_project)
    app.router.add_delete("/api/projects/{slug}", api_archive_project)

    # Agent task routes
    app.router.add_get("/api/agent-tasks", api_get_agent_tasks)
    app.router.add_get("/api/agent-tasks/agent", api_get_agent_level_tasks)
    app.router.add_post("/api/agent-tasks/{id}/approve", api_approve_task)
    app.router.add_post("/api/agent-tasks/{id}/reject", api_reject_task)
    app.router.add_post("/api/agent-tasks/{id}/note", api_add_task_note)

    return app


async def on_startup(app: web.Application):
    """Initialize on application startup."""
    global state, watcher, mqtt_client, tasks_path

    logger.info("=" * 60)
    logger.info(f"Ground Control v{VERSION} starting up")
    logger.info("=" * 60)

    # Debug: Show filesystem root
    logger.info("Filesystem exploration:")
    for check_path in ["/", "/config", "/homeassistant", "/share", "/data"]:
        p = Path(check_path)
        if p.exists():
            try:
                contents = [c.name for c in p.iterdir()][:20]  # First 20 items
                logger.info(f"  {check_path}: {contents}")
            except Exception as e:
                logger.info(f"  {check_path}: Error listing - {e}")
        else:
            logger.info(f"  {check_path}: Does not exist")

    # Load options
    options = load_options()
    logger.info(f"Loaded options: {options}")

    configured_path = options.get("tasks_path", "")

    # Use configured path if valid, otherwise auto-detect
    if configured_path and Path(configured_path).exists():
        tasks_path = configured_path
        logger.info(f"Using configured tasks_path: {tasks_path}")
    else:
        tasks_path = find_tasks_path()
        logger.info(f"Auto-detected tasks_path: {tasks_path}")

    # Load initial state
    await reload_state()

    # Start file watcher
    watcher = TasksWatcher(tasks_path, reload_state)
    watcher.start(asyncio.get_event_loop())

    # Start MQTT client for agent tasks
    async def on_mqtt_update():
        await broadcast({"type": "agent_task_updated"})

    mqtt_client = MQTTTaskClient(on_tasks_update=on_mqtt_update)
    mqtt_client.start(asyncio.get_event_loop())


async def on_cleanup(app: web.Application):
    """Cleanup on application shutdown."""
    global watcher, mqtt_client

    if mqtt_client:
        mqtt_client.stop()

    if watcher:
        watcher.stop()

    # Close WebSocket connections
    for ws in list(websocket_clients):
        await ws.close()


def main():
    """Run the Ground Control server."""
    app = create_app()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    # Get port from environment or default
    port = int(os.environ.get("INGRESS_PORT", 8100))

    logger.info(f"Starting Ground Control on port {port}")
    web.run_app(app, host="0.0.0.0", port=port, print=None)


if __name__ == "__main__":
    main()
