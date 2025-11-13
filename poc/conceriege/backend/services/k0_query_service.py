"""K0 Query Service - Data Access Layer for K0 Memory System.

Provides generic query interface to K0's 8 memory types:
- Episodic: Time-stamped personal events
- Semantic: General knowledge and facts
- Autobiographical: Personal history and identity
- Working: Recent context and short-term memory
- Prospective: Future-oriented intentions
- Spatial: Location-based memories
- Emotional: Affective states
- Procedural: Skills and habits

Architecture:
- K0QueryService: Abstract base class defining interface
- MockK0QueryService: In-memory mock implementation for PoC
- RealK0QueryService: Production implementation (future)
"""

import json
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any

from tests.fixtures.k0_schema import (
    MEMORY_TYPES,
    TABLE_SCHEMAS,
    get_memory_type_for_table,
    search_tables_by_keywords,
)
from tests.fixtures.mock_k0_data import MOCK_DATA as MOCK_DATA_OLD
from tests.fixtures.mock_k0_data import TEST_USER_ID

from backend.config.settings import Settings
from backend.services.llm_client import LLMClient

# Try to import enriched data, fallback to old data if not available
try:
    from tests.fixtures.mock_k0_data_enriched import MOCK_DATA_ENRICHED

    MOCK_DATA = MOCK_DATA_ENRICHED
    print("[K0QueryService] ✅ Using ENRICHED mock data with diverse lifestyle scenarios")
except ImportError:
    MOCK_DATA = MOCK_DATA_OLD
    print("[K0QueryService] ⚠️  Using original mock data (coffee/GERD only)")


class K0QueryService(ABC):
    """Abstract base class for K0 data access.

    Specialists use this interface to query K0 without knowing implementation details.
    Supports schema discovery and semantic table search.
    """

    @abstractmethod
    def query(
        self,
        user_id: str,
        table_name: str,
        filters: dict[str, Any] | None = None,
        time_range: str | tuple[datetime, datetime] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query a specific table with filters.

        Args:
            user_id: User identifier
            table_name: Full table name (e.g., "episodic.diet_logs")
            filters: Column filters (e.g., {"food_item": "coffee", "severity": "high"})
            time_range: Time filter - either string ("last_7_days", "last_30_days", "last_90_days")
                       or tuple of (start_datetime, end_datetime)
            limit: Maximum results to return

        Returns:
            List of matching records as dicts

        Raises:
            ValueError: If table_name doesn't exist or filters invalid
        """
        pass

    @abstractmethod
    def get_schema(self, memory_type: str | None = None) -> dict[str, Any]:
        """Get schema information for memory type(s).

        Args:
            memory_type: Specific memory type (e.g., "episodic") or None for all

        Returns:
            Schema dict with tables, columns, filters, descriptions

        Example:
            schema = service.get_schema("episodic")
            # Returns: {
            #   "episodic.diet_logs": {
            #     "columns": ["id", "timestamp", "food_item", ...],
            #     "filters": ["food_item", "meal_type", "time_range"],
            #     "description": "Personal diet and meal history"
            #   },
            #   ...
            # }
        """
        pass

    @abstractmethod
    def search_tables(self, keywords: list[str]) -> list[tuple[str, int]]:
        """Search for relevant tables by keywords.

        Args:
            keywords: Search keywords (e.g., ["diet", "nutrition", "food"])

        Returns:
            List of (table_name, relevance_score) tuples sorted by relevance

        Example:
            tables = service.search_tables(["GERD", "digestive", "health"])
            # Returns: [("episodic.health_events", 5), ("semantic.health_conditions", 3), ...]
        """
        pass

    @abstractmethod
    def search_tables_semantic(self, natural_query: str) -> list[tuple[str, int]]:
        """Search for relevant tables using natural language query.

        Uses LLM to extract keywords from natural language, then matches against table keywords.

        Args:
            natural_query: Natural language query (e.g., "Find tables about my digestive health issues")

        Returns:
            List of (table_name, relevance_score) tuples sorted by relevance

        Example:
            tables = service.search_tables_semantic("What foods trigger my heartburn?")
            # Returns: [("episodic.diet_logs", 8), ("semantic.food_nutrition", 6), ...]
        """
        pass

    @abstractmethod
    def list_memory_types(self) -> dict[str, dict[str, Any]]:
        """List all available memory types.

        Returns:
            Dict of memory types with metadata

        Example:
            types = service.list_memory_types()
            # Returns: {
            #   "episodic": {
            #     "tables": ["diet_logs", "health_events", ...],
            #     "description": "Time-stamped personal events"
            #   },
            #   ...
            # }
        """
        pass


class MockK0QueryService(K0QueryService):
    """Mock implementation using in-memory test data.

    Uses MOCK_DATA from tests/fixtures/mock_k0_data.py.
    Suitable for PoC and testing without real K0 connection.
    """

    def __init__(self, llm_client: LLMClient | None = None):
        """Initialize mock service with test data.

        Args:
            llm_client: Optional LLM client for semantic search. If None, creates default client.
        """
        self.data = MOCK_DATA
        self.test_user_id = TEST_USER_ID

        # Initialize LLM client for semantic search
        if llm_client is None:
            settings = Settings()
            self.llm_client = LLMClient(settings)
        else:
            self.llm_client = llm_client

    def query(
        self,
        user_id: str,
        table_name: str,
        filters: dict[str, Any] | None = None,
        time_range: str | tuple[datetime, datetime] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query mock data with filtering."""
        # Validate table exists
        if table_name not in TABLE_SCHEMAS:
            raise ValueError(f"Unknown table: {table_name}")

        # Get memory type and table from full name (e.g., "episodic.diet_logs")
        memory_type = get_memory_type_for_table(table_name)
        if not memory_type:
            raise ValueError(f"Invalid table name format: {table_name}")

        # Extract short table name (e.g., "diet_logs" from "episodic.diet_logs")
        short_table_name = table_name.split(".", 1)[1]

        # Get data for this table
        if memory_type not in self.data or short_table_name not in self.data[memory_type]:
            return []

        results = list(self.data[memory_type][short_table_name])

        # Apply time range filter
        if time_range:
            results = self._apply_time_filter(results, time_range, table_name)

        # Apply column filters
        if filters:
            results = self._apply_filters(results, filters)

        # Apply limit
        return results[:limit]

    def _apply_time_filter(
        self,
        records: list[dict[str, Any]],
        time_range: str | tuple[datetime, datetime],
        table_name: str,
    ) -> list[dict[str, Any]]:
        """Apply time range filter to records."""
        # Determine time column (timestamp or date)
        schema = TABLE_SCHEMAS[table_name]
        time_col = None
        if "timestamp" in schema["columns"]:
            time_col = "timestamp"
        elif "date" in schema["columns"]:
            time_col = "date"
        else:
            # No time column, can't filter
            return records

        # Parse time range
        if isinstance(time_range, str):
            now = datetime.now()
            if time_range == "last_7_days":
                start_time = now - timedelta(days=7)
                end_time = now
            elif time_range == "last_30_days":
                start_time = now - timedelta(days=30)
                end_time = now
            elif time_range == "last_90_days":
                start_time = now - timedelta(days=90)
                end_time = now
            else:
                raise ValueError(f"Unknown time range: {time_range}")
        else:
            start_time, end_time = time_range

        # Filter records
        filtered = []
        for record in records:
            if time_col not in record:
                continue

            # Parse record time
            record_time_str = record[time_col]
            try:
                if "T" in record_time_str:
                    # ISO timestamp
                    record_time = datetime.fromisoformat(record_time_str)
                else:
                    # Date only
                    record_time = datetime.fromisoformat(f"{record_time_str}T00:00:00")

                if start_time <= record_time <= end_time:
                    filtered.append(record)
            except (ValueError, AttributeError):
                # Invalid time format, skip
                continue

        return filtered

    def _apply_filters(
        self,
        records: list[dict[str, Any]],
        filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Apply column filters to records."""
        filtered = []
        for record in records:
            match = True
            for key, value in filters.items():
                if key not in record:
                    match = False
                    break

                # Exact match or substring match for strings
                if isinstance(record[key], str) and isinstance(value, str):
                    if value.lower() not in record[key].lower():
                        match = False
                        break
                elif record[key] != value:
                    match = False
                    break

            if match:
                filtered.append(record)

        return filtered

    def get_schema(self, memory_type: str | None = None) -> dict[str, Any]:
        """Get schema for memory type(s)."""
        if memory_type is None:
            # Return all schemas
            return TABLE_SCHEMAS

        # Validate memory type
        if memory_type not in MEMORY_TYPES:
            raise ValueError(f"Unknown memory type: {memory_type}")

        # Return schemas for this memory type
        prefix = f"{memory_type}."
        return {
            table: schema for table, schema in TABLE_SCHEMAS.items() if table.startswith(prefix)
        }

    def search_tables(self, keywords: list[str]) -> list[tuple[str, int]]:
        """Search tables by keywords."""
        return search_tables_by_keywords(keywords)

    def search_tables_semantic(self, natural_query: str) -> list[tuple[str, int]]:
        """Search for relevant tables using natural language query.

        Uses LLM (fast profile) to extract keywords from natural language,
        then matches against table keywords.

        Args:
            natural_query: Natural language query

        Returns:
            List of (table_name, relevance_score) tuples sorted by relevance
        """
        # Use LLM to extract keywords
        prompt = f"""Extract relevant search keywords from this natural language query.
Return ONLY a JSON array of keywords (lowercase, no explanation).

Query: "{natural_query}"

Example output format: ["keyword1", "keyword2", "keyword3"]

Keywords:"""

        try:
            # Use synthesis profile for keyword extraction (fast profile returns empty)
            response = self.llm_client.generate(
                prompt=prompt,
                profile="synthesis",
                max_tokens=100,
            )

            # Parse JSON response
            keywords_text = response.strip()

            # If response is empty, raise exception to trigger fallback
            if not keywords_text:
                raise ValueError("Empty LLM response")

            # Try to extract JSON array from response
            if "[" in keywords_text and "]" in keywords_text:
                start = keywords_text.index("[")
                end = keywords_text.rindex("]") + 1
                keywords_json = keywords_text[start:end]
                keywords = json.loads(keywords_json)
            else:
                # Fallback: split by common delimiters
                keywords = [k.strip().strip("\"'") for k in keywords_text.split(",")]

            # Ensure keywords is a list of strings
            if not isinstance(keywords, list):
                keywords = [str(keywords)]

            keywords = [str(k).lower() for k in keywords if k]

            # If we got no keywords, trigger fallback
            if not keywords:
                raise ValueError("No keywords extracted")

        except Exception:
            # Fallback to simple word extraction if LLM fails
            import re

            keywords = re.findall(r"\b\w+\b", natural_query.lower())
            keywords = [k for k in keywords if len(k) > 2]  # Filter short words

        # Use keyword search with extracted keywords
        return search_tables_by_keywords(keywords)

    def list_memory_types(self) -> dict[str, dict[str, Any]]:
        """List all memory types."""
        return MEMORY_TYPES


# Factory function for easy instantiation
def create_k0_service(mock: bool = True, llm_client: LLMClient | None = None) -> K0QueryService:
    """Create K0 query service instance.

    Args:
        mock: If True, return mock service; if False, return real service
        llm_client: Optional LLM client for semantic search

    Returns:
        K0QueryService instance
    """
    if mock:
        return MockK0QueryService(llm_client=llm_client)
    else:
        raise NotImplementedError("Real K0 service not yet implemented")
