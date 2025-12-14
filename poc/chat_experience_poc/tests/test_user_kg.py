"""
Tests for User Knowledge Graph (UserKG) query interface and agent integration.
"""

from datetime import datetime, timedelta

import pytest
from l5_infrastructure.user_kg.kg_query_interface import UserKG
from l5_infrastructure.user_kg.kg_schema import NodeType


@pytest.fixture()
def temp_userkg(tmp_path, monkeypatch):
    """Provide a fresh UserKG instance on a temporary database file."""
    db_path = tmp_path / "test_user_kg.db"

    # Initialize singleton with this db path
    kg = UserKG(str(db_path))

    # Clear any data to start
    kg.clear_all_data()

    yield kg

    # Cleanup (no-op close)
    kg.close()


def test_userkg_add_and_query_profile(temp_userkg: UserKG):
    # Create a Person node (person_id empty means self-reference after insert)
    user_id = temp_userkg.add_node(
        NodeType.PERSON,
        person_id="",
        properties={
            "name": "Test User",
            "age": 30,
            "locale": "en_US",
            "timezone": "US/Pacific",
        },
    )

    profile = temp_userkg.get_user_profile(user_id)
    assert profile is not None
    assert profile["node_type"] == NodeType.PERSON.value
    assert profile["properties"]["name"] == "Test User"


def test_userkg_preferences_and_goals(temp_userkg: UserKG):
    # Setup user
    user_id = temp_userkg.add_node(
        NodeType.PERSON,
        person_id="",
        properties={
            "name": "Alice",
            "age": 28,
            "locale": "en_US",
            "timezone": "US/Pacific",
        },
    )

    # Add preferences
    temp_userkg.add_node(
        NodeType.PREFERENCE,
        person_id=user_id,
        properties={
            "category": "food",
            "value": "Italian",
            "strength": 0.9,
            "source": "stated",
        },
    )
    temp_userkg.add_node(
        NodeType.PREFERENCE,
        person_id=user_id,
        properties={
            "category": "exercise",
            "value": "cycling",
            "strength": 0.7,
            "source": "inferred",
        },
    )

    # Add goal
    temp_userkg.add_node(
        NodeType.GOAL,
        person_id=user_id,
        properties={
            "description": "Improve knee strength",
            "deadline": (datetime.utcnow() + timedelta(days=30)).date().isoformat(),
            "progress": 0.4,
            "active": True,
        },
    )

    prefs_all = temp_userkg.get_preferences(user_id)
    assert len(prefs_all) >= 2

    prefs_food = temp_userkg.get_preferences(user_id, category="food")
    assert len(prefs_food) == 1
    assert prefs_food[0]["properties"]["value"] == "Italian"

    goals = temp_userkg.get_active_goals(user_id)
    assert len(goals) == 1
    assert goals[0]["properties"]["description"].startswith("Improve")


@pytest.mark.asyncio
async def test_agentbase_query_user_kg(monkeypatch, temp_userkg: UserKG):
    """Patch get_user_kg() to return our temp instance and validate agent API shape."""
    # Seed a simple user with preferences
    user_id = temp_userkg.add_node(
        NodeType.PERSON,
        person_id="",
        properties={
            "name": "Bob",
            "age": 40,
            "locale": "en_US",
            "timezone": "US/Pacific",
        },
    )
    temp_userkg.add_node(
        NodeType.PREFERENCE,
        person_id=user_id,
        properties={
            "category": "health",
            "value": "low_sodium",
            "strength": 0.8,
            "source": "stated",
        },
    )

    # Patch get_user_kg to return temp instance
    monkeypatch.setattr("l5_infrastructure.user_kg.get_user_kg", lambda: temp_userkg)

    # Minimal fake agent instance using AgentBase via a simple subclass
    from l3_execution.agents.agent_base import AgentBase

    class TestAgent(AgentBase):
        async def process_message(self, message):
            return None

    agent = TestAgent(
        agent_id="test_agent",
        agent_type="test",
        session_id="sess",
        groq_client=None,
    )

    res = await agent.query_user_kg("get_preferences", {"user_id": user_id})

    assert res["status"] == "success"
    assert res["query_type"] == "get_preferences"
    assert isinstance(res["data"], list)
    assert any(p["properties"]["category"] == "health" for p in res["data"])
