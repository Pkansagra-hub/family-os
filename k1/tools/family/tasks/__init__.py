"""k1.tools.family.tasks -- Family Tasks adapter (M15 §E15.2).

Public exports
--------------
* :data:`TASKS_DEFINITION` -- the declarative :class:`ToolDefinition`.
* :class:`TaskItem`, :class:`TaskList` -- the typed entities.
* :class:`TasksToolService` -- the :class:`BaseToolService` subclass.
"""

from k1.tools.family.tasks.definition import TASKS_DEFINITION
from k1.tools.family.tasks.schema import TaskItem, TaskList
from k1.tools.family.tasks.service import TasksToolService

__all__ = [
    "TASKS_DEFINITION",
    "TaskItem",
    "TaskList",
    "TasksToolService",
]
