"""Writer for .tasks/ markdown files."""

import yaml
from pathlib import Path
from datetime import date, datetime
from typing import Dict, List

from models import Task, Project, BucketsFile, BUCKETS


def increment_version(version: str, level: str = "minor") -> str:
    """
    Increment semantic version.
    level: 'major', 'minor', or 'patch'
    """
    parts = version.split(".")
    if len(parts) != 3:
        parts = ["1", "0", "0"]

    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

    if level == "major":
        major += 1
        minor = 0
        patch = 0
    elif level == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1

    return f"{major}.{minor}.{patch}"


def task_to_line(task: Task) -> str:
    """Convert a task to a markdown line."""
    parts = []

    # Completed date prefix
    if task.completed_date:
        parts.append(f"**{task.completed_date}**:")

    # Task ID
    if task.id:
        parts.append(f"[{task.id}]")

    # Subject
    parts.append(task.subject)

    line = " ".join(parts)

    # Project suffix
    if task.project:
        line += f" (project: {task.project})"

    # Blocked by suffix
    if task.blocked_by:
        blocked_str = ", ".join(task.blocked_by)
        line += f" (blocked by: {blocked_str})"

    return f"- {line}"


def write_buckets_file(path: str, buckets: BucketsFile):
    """Write buckets.md file."""
    # Update metadata
    buckets.version = increment_version(buckets.version, "minor")
    buckets.updated = date.today().isoformat()
    buckets.update_counts()

    # Build frontmatter
    frontmatter = {
        "title": "Task Buckets",
        "type": "buckets",
        "version": buckets.version,
        "created": buckets.created or date.today().isoformat(),
        "updated": buckets.updated,
        "description": "Current state of all tasks organized by workflow bucket",
        "next_id": buckets.next_id,
        "task_count": buckets.task_count,
    }

    # Build markdown body
    bucket_headers = {
        "active": ("Active", "*(Currently being worked on)*"),
        "work_queue": ("Work Queue", "*(Ready and desired to be worked next)*"),
        "completed": ("Completed", "*(Historical record)*"),
        "cleanup": ("Cleanup", "*(Tech debt and tidying)*"),
        "investigation": ("Investigation", "*(Needs research or verification)*"),
        "planning": ("Planning", "*(Needs design before actionable)*"),
        "brainstorm": ("Brainstorm", "*(Raw ideas, not committed)*"),
    }

    lines = ["# Task Buckets", ""]

    for bucket in BUCKETS:
        header, description = bucket_headers.get(bucket, (bucket.title(), ""))
        lines.append(f"## {header}")
        lines.append(description)
        lines.append("")

        tasks = buckets.tasks.get(bucket, [])
        if tasks:
            for task in tasks:
                lines.append(task_to_line(task))
        else:
            lines.append("— empty —")

        lines.append("")

    # Write file
    yaml_str = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
    content = f"---\n{yaml_str}---\n\n" + "\n".join(lines)

    Path(path).write_text(content)


def write_project_file(path: str, project: Project, tasks: List[Task] = None):
    """Write a project file."""
    frontmatter = {
        "title": f"Project: {project.name}",
        "type": "project",
        "slug": project.slug,
        "version": "1.0.0",
        "created": date.today().isoformat(),
        "updated": date.today().isoformat(),
        "status": project.status,
        "goal": project.goal,
    }

    lines = [
        f"# Project: {project.name}",
        "",
        f"**Status:** {project.status.replace('_', ' ').title()}",
        f"**Goal:** {project.goal}",
        "",
        "---",
        "",
    ]

    if tasks:
        completed = [t for t in tasks if t.bucket == "completed"]
        backlog = [t for t in tasks if t.bucket != "completed"]

        lines.append("## Completed")
        for task in completed:
            lines.append(f"- [x] {task.subject}")
        if not completed:
            lines.append("*(none yet)*")
        lines.append("")

        lines.append("## Backlog")
        for task in backlog:
            lines.append(f"- [ ] {task.subject} (bucket: {task.bucket.title()})")
        if not backlog:
            lines.append("*(none)*")
        lines.append("")

    yaml_str = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
    content = f"---\n{yaml_str}---\n\n" + "\n".join(lines)

    Path(path).write_text(content)


def move_task(buckets: BucketsFile, task_id: str, target_bucket: str) -> bool:
    """
    Move a task to a different bucket.
    Returns True if successful, False if invalid move.
    """
    # Find the task
    task = None
    source_bucket = None

    for bucket, tasks in buckets.tasks.items():
        for t in tasks:
            if t.id == task_id:
                task = t
                source_bucket = bucket
                break
        if task:
            break

    if not task:
        return False

    # Validate move
    if not task.can_move_to(target_bucket):
        return False

    # Check blocked status
    if target_bucket in ("work_queue", "active") and task.is_blocked():
        return False

    # Remove from source
    buckets.tasks[source_bucket].remove(task)

    # Update task
    task.bucket = target_bucket
    if target_bucket == "completed":
        task.completed_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Add to target
    buckets.tasks[target_bucket].append(task)

    return True


def create_task(
    buckets: BucketsFile,
    subject: str,
    bucket: str = "brainstorm",
    project: str = "",
    description: str = "",
) -> Task:
    """Create a new task with auto-assigned ID."""
    task = Task(
        id=buckets.assign_next_id(),
        subject=subject,
        bucket=bucket,
        project=project,
        description=description,
        created_date=date.today().isoformat(),
    )

    if bucket not in buckets.tasks:
        buckets.tasks[bucket] = []

    buckets.tasks[bucket].append(task)

    return task


def complete_task(buckets: BucketsFile, task_id: str) -> bool:
    """Mark a task as completed."""
    return move_task(buckets, task_id, "completed")


def delete_task(buckets: BucketsFile, task_id: str) -> bool:
    """Delete a task from buckets."""
    for bucket, tasks in buckets.tasks.items():
        for task in tasks:
            if task.id == task_id:
                tasks.remove(task)
                return True
    return False


def slugify(name: str) -> str:
    """Convert a name to a URL-safe slug."""
    import re
    # Lowercase, replace spaces with hyphens, remove non-alphanumeric
    slug = name.lower().strip()
    slug = re.sub(r'\s+', '-', slug)
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')


def create_project(
    tasks_path: str,
    name: str,
    goal: str,
    description: str = "",
) -> Project:
    """Create a new project with generated slug."""
    slug = slugify(name)

    project = Project(
        slug=slug,
        name=name,
        status="not_started",
        goal=goal,
        description=description,
    )

    # Ensure projects directory exists
    projects_dir = Path(tasks_path) / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)

    # Write project file
    project_path = projects_dir / f"{slug}.md"
    write_project_file(str(project_path), project)

    return project


def update_project(
    tasks_path: str,
    slug: str,
    status: str = None,
    goal: str = None,
    name: str = None,
) -> Project:
    """Update an existing project."""
    from parser import parse_project_file

    project_path = Path(tasks_path) / "projects" / f"{slug}.md"
    if not project_path.exists():
        return None

    # Load existing project
    project = parse_project_file(str(project_path))
    if not project:
        return None

    # Update fields
    if status is not None:
        project.status = status
    if goal is not None:
        project.goal = goal
    if name is not None:
        project.name = name

    # Write updated project
    write_project_file(str(project_path), project)

    return project


def archive_project(tasks_path: str, slug: str) -> bool:
    """Archive a project by setting its status to 'archived'."""
    project = update_project(tasks_path, slug, status="archived")
    return project is not None
