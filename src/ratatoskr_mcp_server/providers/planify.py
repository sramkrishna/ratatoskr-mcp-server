"""Planify tasks provider for Ratatoskr MCP server."""

from typing import Optional
from .base import ResourceProvider, ResourceData
from ..utils.planify import PlanifyManager


class PlanifyProvider(ResourceProvider):
    """Provides Planify task data."""

    def __init__(self):
        """Initialize the Planify provider."""
        self.manager = PlanifyManager()

    async def get_resource(self) -> ResourceData:
        """Get all tasks from Planify.

        Returns:
            ResourceData containing all tasks.
        """
        return await self.query_tasks()

    async def query_tasks(
        self,
        completed: Optional[bool] = None,
        project_id: Optional[str] = None,
        priority: Optional[int] = None,
        has_due_date: Optional[bool] = None,
        due_date: Optional[str] = None,
        limit: Optional[int] = 50
    ) -> ResourceData:
        """Query tasks with filters.

        Args:
            completed: Filter by completion status (None = all).
            project_id: Filter by project ID.
            priority: Filter by priority (1-4, where 1 is low, 4 is urgent).
            has_due_date: Filter tasks that have a due date.
            due_date: Filter tasks by specific due date (ISO format: YYYY-MM-DD).
            limit: Maximum number of tasks to return.

        Returns:
            ResourceData containing filtered tasks.
        """
        tasks = self.manager.get_tasks(
            completed=completed,
            project_id=project_id,
            priority=priority,
            has_due_date=has_due_date,
            due_date=due_date,
            limit=limit
        )

        task_list = []
        for task in tasks:
            task_dict = {
                "id": task.id,
                "content": task.content,
                "description": task.description,
                "due_date": task.due_date,
                "added_at": task.added_at,
                "completed_at": task.completed_at,
                "updated_at": task.updated_at,
                "project_id": task.project_id,
                "project_name": task.project_name,
                "priority": task.priority,
                "checked": task.checked,
                "pinned": task.pinned,
                "labels": task.labels
            }
            task_list.append(task_dict)

        result = {
            "total_tasks": len(task_list),
            "tasks": task_list
        }

        return ResourceData(content=result)

    async def get_task(self, task_id: str) -> ResourceData:
        """Get a specific task by ID.

        Args:
            task_id: The task ID to retrieve.

        Returns:
            ResourceData containing the task, or error if not found.
        """
        task = self.manager.get_task_by_id(task_id)

        if task is None:
            return ResourceData(
                content={
                    "error": "Task not found",
                    "task_id": task_id
                }
            )

        task_dict = {
            "id": task.id,
            "content": task.content,
            "description": task.description,
            "due_date": task.due_date,
            "added_at": task.added_at,
            "completed_at": task.completed_at,
            "updated_at": task.updated_at,
            "project_id": task.project_id,
            "project_name": task.project_name,
            "priority": task.priority,
            "checked": task.checked,
            "pinned": task.pinned,
            "labels": task.labels
        }

        return ResourceData(content={"task": task_dict})

    async def get_projects(self) -> ResourceData:
        """Get all available projects.

        Returns:
            ResourceData containing all projects.
        """
        projects = self.manager.get_projects()

        project_list = [
            {"id": proj_id, "name": name}
            for proj_id, name in projects.items()
        ]

        return ResourceData(
            content={
                "total_projects": len(project_list),
                "projects": project_list
            }
        )
