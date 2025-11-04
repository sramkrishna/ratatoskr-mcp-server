"""Planify task manager integration utilities."""

import json
import os
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class PlanifyTask:
    """Represents a task from Planify."""
    id: str
    content: str
    description: Optional[str] = None
    due_date: Optional[str] = None
    added_at: Optional[str] = None
    completed_at: Optional[str] = None
    updated_at: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    priority: int = 1
    checked: bool = False
    is_deleted: bool = False
    pinned: bool = False
    labels: Optional[str] = None


class PlanifyManager:
    """Manager for accessing Planify tasks via SQLite database."""

    PLANIFY_APP_ID = "io.github.alainm23.planify"

    def __init__(self, db_path: Optional[str] = None):
        """Initialize Planify manager.

        Args:
            db_path: Path to Planify database. If None, uses default location.
        """
        if db_path is None:
            db_path = self._get_default_db_path()

        self.db_path = db_path
        self._projects_cache = {}

    @classmethod
    def _get_default_db_path(cls) -> str:
        """Get the default Planify database path."""
        home = Path.home()
        return str(home / f".var/app/{cls.PLANIFY_APP_ID}/data/{cls.PLANIFY_APP_ID}/database.db")

    @classmethod
    def is_planify_installed(cls) -> bool:
        """Check if Planify is installed as a Flatpak.

        Returns:
            True if Planify is installed, False otherwise.
        """
        try:
            result = subprocess.run(
                ["flatpak", "list", "--app", "--columns=application"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return cls.PLANIFY_APP_ID in result.stdout
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    @classmethod
    def is_available(cls) -> bool:
        """Check if Planify is installed and database exists.

        Returns:
            True if Planify is available, False otherwise.
        """
        if not cls.is_planify_installed():
            return False

        db_path = cls._get_default_db_path()
        return os.path.exists(db_path)

    def _load_projects(self) -> dict:
        """Load projects from database into cache.

        Returns:
            Dictionary mapping project IDs to project names.
        """
        if self._projects_cache:
            return self._projects_cache

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, name FROM Projects WHERE is_deleted = 0")
                self._projects_cache = {row[0]: row[1] for row in cursor.fetchall()}
        except sqlite3.Error as e:
            print(f"Error loading projects: {e}")
            self._projects_cache = {}

        return self._projects_cache

    def _parse_due_date(self, due_json: str) -> Optional[str]:
        """Parse the due date JSON field.

        Args:
            due_json: JSON string containing due date information.

        Returns:
            ISO format date string if date exists, None otherwise.
        """
        if not due_json:
            return None

        try:
            due_data = json.loads(due_json)
            date_str = due_data.get("date", "")
            if date_str:
                return date_str
        except (json.JSONDecodeError, KeyError):
            pass

        return None

    def get_tasks(
        self,
        completed: Optional[bool] = None,
        project_id: Optional[str] = None,
        priority: Optional[int] = None,
        has_due_date: Optional[bool] = None,
        due_date: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[PlanifyTask]:
        """Get tasks with optional filters.

        Args:
            completed: Filter by completion status (None = all).
            project_id: Filter by project ID.
            priority: Filter by priority (1-4, where 1 is low, 4 is urgent).
            has_due_date: Filter tasks that have a due date.
            due_date: Filter tasks by specific due date (ISO format: YYYY-MM-DD).
            limit: Maximum number of tasks to return.

        Returns:
            List of PlanifyTask objects.
        """
        projects = self._load_projects()

        query = "SELECT id, content, description, due, added_at, completed_at, updated_at, " \
                "project_id, priority, checked, is_deleted, pinned, labels " \
                "FROM Items WHERE is_deleted = 0"

        params = []

        if completed is not None:
            query += " AND checked = ?"
            params.append(1 if completed else 0)

        if project_id is not None:
            query += " AND project_id = ?"
            params.append(project_id)

        if priority is not None:
            query += " AND priority = ?"
            params.append(priority)

        query += " ORDER BY priority DESC, child_order ASC"

        if limit is not None:
            query += f" LIMIT {int(limit)}"

        tasks = []

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)

                for row in cursor.fetchall():
                    task_id, content, description, due_json, added_at, completed_at, \
                        updated_at, proj_id, priority_val, checked, is_deleted, pinned, labels = row

                    task_due_date = self._parse_due_date(due_json)

                    # Apply has_due_date filter if specified
                    if has_due_date is not None:
                        if has_due_date and not task_due_date:
                            continue
                        if not has_due_date and task_due_date:
                            continue

                    # Apply due_date filter if specified
                    if due_date is not None:
                        if task_due_date != due_date:
                            continue

                    project_name = projects.get(proj_id, "Unknown")

                    tasks.append(PlanifyTask(
                        id=task_id,
                        content=content,
                        description=description,
                        due_date=task_due_date,
                        added_at=added_at,
                        completed_at=completed_at,
                        updated_at=updated_at,
                        project_id=proj_id,
                        project_name=project_name,
                        priority=priority_val,
                        checked=bool(checked),
                        is_deleted=bool(is_deleted),
                        pinned=bool(pinned),
                        labels=labels
                    ))
        except sqlite3.Error as e:
            print(f"Error querying tasks: {e}")

        return tasks

    def get_task_by_id(self, task_id: str) -> Optional[PlanifyTask]:
        """Get a specific task by ID.

        Args:
            task_id: The task ID.

        Returns:
            PlanifyTask object if found, None otherwise.
        """
        projects = self._load_projects()

        query = "SELECT id, content, description, due, added_at, completed_at, updated_at, " \
                "project_id, priority, checked, is_deleted, pinned, labels " \
                "FROM Items WHERE id = ? AND is_deleted = 0"

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(query, (task_id,))
                row = cursor.fetchone()

                if row:
                    task_id, content, description, due_json, added_at, completed_at, \
                        updated_at, proj_id, priority_val, checked, is_deleted, pinned, labels = row

                    due_date = self._parse_due_date(due_json)
                    project_name = projects.get(proj_id, "Unknown")

                    return PlanifyTask(
                        id=task_id,
                        content=content,
                        description=description,
                        due_date=due_date,
                        added_at=added_at,
                        completed_at=completed_at,
                        updated_at=updated_at,
                        project_id=proj_id,
                        project_name=project_name,
                        priority=priority_val,
                        checked=bool(checked),
                        is_deleted=bool(is_deleted),
                        pinned=bool(pinned),
                        labels=labels
                    )
        except sqlite3.Error as e:
            print(f"Error getting task: {e}")

        return None

    def get_projects(self) -> dict:
        """Get all available projects.

        Returns:
            Dictionary mapping project IDs to project names.
        """
        return self._load_projects()

    @classmethod
    def quick_add(cls) -> dict:
        """Launch Planify quick-add dialog for adding a new todo.

        Returns:
            Dictionary with 'success' boolean and optional 'error' message.
        """
        try:
            result = subprocess.run(
                ['flatpak', 'run', '--command=io.github.alainm23.planify.quick-add', cls.PLANIFY_APP_ID],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout for user input
            )

            if result.returncode == 0:
                return {"success": True}
            else:
                return {"success": False, "error": f"Dialog returned error: {result.stderr}"}

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Dialog timed out after 5 minutes"}
        except FileNotFoundError:
            return {"success": False, "error": "Flatpak not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
