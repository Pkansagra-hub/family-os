"""k1.tools.family.calendar -- Family Calendar adapter (M15 §E15.1).

Public exports
--------------
* :data:`CALENDAR_DEFINITION` -- the declarative :class:`ToolDefinition`.
* :class:`CalendarEvent`, :class:`ExternalFeed` -- the typed entities.
* :class:`CalendarToolService` -- the :class:`BaseToolService` subclass.
"""

from k1.tools.family.calendar.definition import CALENDAR_DEFINITION
from k1.tools.family.calendar.schema import CalendarEvent, ExternalFeed
from k1.tools.family.calendar.service import CalendarToolService

__all__ = [
    "CALENDAR_DEFINITION",
    "CalendarEvent",
    "CalendarToolService",
    "ExternalFeed",
]
