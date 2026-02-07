"""
Tests for Travel Tools
======================

Tests for Epic 2.1: Travel Tools implementation.
Verifies all 9 travel tools work correctly with mock data.
"""

from poc.session_state_demo.anniversary_demo.tools.travel import (
    TRAVEL_TOOLS,
    BookingStore,
    book_accommodation,
    book_restaurant,
    book_spa_service,
    execute_travel_tool,
    get_accommodation_details,
    get_restaurant_details,
    plan_route,
    search_accommodations,
    search_activities,
    search_restaurants,
)


class TestSearchAccommodations:
    """Tests for search_accommodations tool."""

    def test_basic_search_sonoma(self):
        """Test basic search in Sonoma returns results."""
        result = search_accommodations(
            location="Sonoma",
            check_in_date="2026-02-14",
            nights=2,
        )

        assert result["success"] is True
        assert result["location"] == "Sonoma"
        assert result["results_count"] > 0
        assert len(result["results"]) > 0

        # Verify result structure
        first_result = result["results"][0]
        assert "name" in first_result
        assert "price_per_night" in first_result
        assert "rating" in first_result
        assert "amenities" in first_result

    def test_search_with_budget_filter(self):
        """Test search filters by budget correctly."""
        result = search_accommodations(
            location="Sonoma",
            check_in_date="2026-02-14",
            nights=2,
            budget_per_night=250,
        )

        assert result["success"] is True
        for accommodation in result["results"]:
            assert accommodation["price_per_night"] <= 250

    def test_search_with_party_size(self):
        """Test search includes party size in params."""
        result = search_accommodations(
            location="Sonoma",
            check_in_date="2026-02-14",
            nights=2,
            party_size=4,
        )

        assert result["success"] is True
        assert result["party_size"] == 4

    def test_search_unknown_location_returns_empty(self):
        """Test search in unknown location returns empty results."""
        result = search_accommodations(
            location="Unknown City",
            check_in_date="2026-02-14",
            nights=2,
        )

        assert result["success"] is True
        assert result["results_count"] == 0
        assert len(result["results"]) == 0


class TestGetAccommodationDetails:
    """Tests for get_accommodation_details tool."""

    def test_get_vineyard_inn_details(self):
        """Test getting details for Vineyard Inn."""
        result = get_accommodation_details(name="Vineyard Inn")

        assert result["success"] is True
        assert "details" in result

        details = result["details"]
        assert details["name"] == "Vineyard Inn"
        assert details["price_per_night"] == 289.0
        assert len(details["amenities"]) > 0
        assert len(details["room_types"]) > 0
        assert "policies" in details
        assert "contact" in details

    def test_get_unknown_accommodation(self):
        """Test getting details for unknown accommodation."""
        result = get_accommodation_details(name="Unknown Hotel")

        assert result["success"] is False
        assert "error" in result
        assert "suggestions" in result


class TestBookAccommodation:
    """Tests for book_accommodation tool."""

    def setup_method(self):
        """Clear booking store before each test."""
        BookingStore.get_instance().clear()

    def test_book_vineyard_inn(self):
        """Test booking Vineyard Inn successfully."""
        result = book_accommodation(
            name="Vineyard Inn",
            location="Sonoma",
            check_in_date="2026-02-14",
            nights=2,
            guests=2,
        )

        assert result["success"] is True
        assert "confirmation" in result

        conf = result["confirmation"]
        assert conf["booking_type"] == "accommodation"
        assert conf["name"] == "Vineyard Inn"
        assert conf["status"] == "confirmed"
        assert conf["total_cost"] == 289.0 * 2  # 2 nights
        assert conf["confirmation_number"].startswith("ACC-")

    def test_book_with_special_requests(self):
        """Test booking with special requests."""
        result = book_accommodation(
            name="Vineyard Inn",
            location="Sonoma",
            check_in_date="2026-02-14",
            nights=2,
            guests=2,
            special_requests=["Late check-out", "Champagne on arrival"],
        )

        assert result["success"] is True
        assert "Champagne on arrival" in result["confirmation"]["details"]["special_requests"]

    def test_book_unknown_accommodation(self):
        """Test booking unknown accommodation fails."""
        result = book_accommodation(
            name="Unknown Hotel",
            location="Somewhere",
            check_in_date="2026-02-14",
            nights=2,
            guests=2,
        )

        assert result["success"] is False
        assert "error" in result


class TestSearchRestaurants:
    """Tests for search_restaurants tool."""

    def test_basic_search_sonoma(self):
        """Test basic restaurant search in Sonoma."""
        result = search_restaurants(location="Sonoma")

        assert result["success"] is True
        assert result["results_count"] > 0

        first_result = result["results"][0]
        assert "name" in first_result
        assert "cuisine" in first_result
        assert "price_range" in first_result

    def test_search_with_cuisine_filter(self):
        """Test search filters by cuisine."""
        result = search_restaurants(
            location="Sonoma",
            cuisine="Italian",
        )

        assert result["success"] is True
        for restaurant in result["results"]:
            assert "italian" in restaurant["cuisine"].lower()

    def test_search_with_allergy_filter(self):
        """Test search notes allergy restrictions."""
        result = search_restaurants(
            location="Sonoma",
            avoid_ingredients=["shellfish"],
        )

        assert result["success"] is True
        assert len(result["allergy_notes"]) > 0
        assert "shellfish" in result["allergy_notes"][0]


class TestGetRestaurantDetails:
    """Tests for get_restaurant_details tool."""

    def test_get_della_santinas_details(self):
        """Test getting details for Della Santina's."""
        result = get_restaurant_details(name="Della Santina's")

        assert result["success"] is True
        assert "details" in result

        details = result["details"]
        assert details["name"] == "Della Santina's"
        assert "Italian" in details["cuisine"]
        assert len(details["menu_highlights"]) > 0
        assert len(details["birthday_specials"]) > 0

    def test_get_details_with_birthday_query(self):
        """Test getting birthday-focused details."""
        result = get_restaurant_details(
            name="Della Santina's",
            query="birthday_specials",
        )

        assert result["success"] is True
        assert "focused_info" in result
        assert result["focused_info"]["type"] == "birthday_specials"


class TestBookRestaurant:
    """Tests for book_restaurant tool."""

    def setup_method(self):
        """Clear booking store before each test."""
        BookingStore.get_instance().clear()

    def test_book_della_santinas(self):
        """Test booking Della Santina's successfully."""
        result = book_restaurant(
            restaurant_name="Della Santina's",
            date="2026-02-14",
            time="19:00",
            party_size=2,
        )

        assert result["success"] is True
        assert "confirmation" in result

        conf = result["confirmation"]
        assert conf["booking_type"] == "restaurant"
        assert conf["confirmation_number"].startswith("RES-")

    def test_book_with_allergy_request(self):
        """Test booking with allergy noted."""
        result = book_restaurant(
            restaurant_name="Della Santina's",
            date="2026-02-14",
            time="19:00",
            party_size=2,
            special_requests=["50th birthday celebration", "shellfish allergy - IMPORTANT"],
        )

        assert result["success"] is True
        # Check that allergy note was added
        notes_text = " ".join(result["confirmation"]["notes"])
        assert "ALLERGY" in notes_text


class TestPlanRoute:
    """Tests for plan_route tool."""

    def test_fastest_route_sf_to_sonoma(self):
        """Test fastest route from SF to Sonoma."""
        result = plan_route(
            origin="San Francisco",
            destination="Sonoma",
            preference="fastest",
        )

        assert result["success"] is True
        assert "route" in result

        route = result["route"]
        assert route["origin"] == "San Francisco"
        assert route["destination"] == "Sonoma"
        assert route["route_type"] == "fastest"
        assert route["duration_minutes"] < 100  # Should be faster than scenic

    def test_scenic_route_sf_to_sonoma(self):
        """Test scenic route from SF to Sonoma."""
        result = plan_route(
            origin="San Francisco",
            destination="Sonoma",
            preference="scenic",
        )

        assert result["success"] is True
        route = result["route"]
        assert route["route_type"] == "scenic"
        assert len(route["highlights"]) > 0
        assert "Golden Gate Bridge" in route["highlights"][0]

    def test_unknown_route_returns_estimate(self):
        """Test unknown route returns estimated route."""
        result = plan_route(
            origin="Los Angeles",
            destination="Seattle",
        )

        assert result["success"] is True
        assert "note" in result


class TestSearchActivities:
    """Tests for search_activities tool."""

    def test_basic_search_sonoma(self):
        """Test basic activity search in Sonoma."""
        result = search_activities(location="Sonoma")

        assert result["success"] is True
        assert result["results_count"] > 0

        first_result = result["results"][0]
        assert "name" in first_result
        assert "category" in first_result
        assert "price" in first_result

    def test_search_relaxation_activities(self):
        """Test search for relaxation activities."""
        result = search_activities(
            location="Vineyard Inn",
            category="relaxation",
        )

        assert result["success"] is True
        for activity in result["results"]:
            assert activity["category"] == "relaxation"


class TestBookSpaService:
    """Tests for book_spa_service tool."""

    def setup_method(self):
        """Clear booking store before each test."""
        BookingStore.get_instance().clear()

    def test_book_couples_massage(self):
        """Test booking couples massage."""
        result = book_spa_service(
            location="Vineyard Inn",
            service="couples_massage",
            date="2026-02-15",
            time="11:00",
            guests=2,
        )

        assert result["success"] is True
        assert "confirmation" in result

        conf = result["confirmation"]
        assert conf["booking_type"] == "spa"
        assert conf["confirmation_number"].startswith("SPA-")
        assert conf["total_cost"] == 320.0

    def test_book_unknown_spa(self):
        """Test booking at unknown spa fails."""
        result = book_spa_service(
            location="Unknown Spa",
            service="massage",
            date="2026-02-15",
            time="10:00",
        )

        assert result["success"] is False
        assert "available_locations" in result


class TestExecuteTravelTool:
    """Tests for execute_travel_tool dispatcher."""

    def test_execute_known_tool(self):
        """Test executing a known tool by name."""
        result = execute_travel_tool(
            "search_accommodations",
            {"location": "Sonoma", "check_in_date": "2026-02-14", "nights": 2},
        )

        assert result["success"] is True
        assert result["results_count"] > 0

    def test_execute_unknown_tool(self):
        """Test executing unknown tool returns error."""
        result = execute_travel_tool(
            "unknown_tool",
            {},
        )

        assert result["success"] is False
        assert "available_tools" in result

    def test_execute_with_invalid_params(self):
        """Test executing tool with invalid params returns error."""
        result = execute_travel_tool(
            "search_accommodations",
            {"wrong_param": "value"},
        )

        assert result["success"] is False


class TestBookingStore:
    """Tests for BookingStore singleton."""

    def setup_method(self):
        """Clear booking store before each test."""
        BookingStore.get_instance().clear()

    def test_singleton_instance(self):
        """Test BookingStore is a singleton."""
        store1 = BookingStore.get_instance()
        store2 = BookingStore.get_instance()
        assert store1 is store2

    def test_store_and_retrieve_booking(self):
        """Test storing and retrieving bookings."""
        # Make a booking
        result = book_accommodation(
            name="Vineyard Inn",
            location="Sonoma",
            check_in_date="2026-02-14",
            nights=2,
            guests=2,
        )

        conf_number = result["confirmation"]["confirmation_number"]

        # Retrieve it
        store = BookingStore.get_instance()
        booking = store.get_booking(conf_number)

        assert booking is not None
        assert booking.name == "Vineyard Inn"

    def test_get_all_bookings(self):
        """Test getting all bookings."""
        # Make multiple bookings
        book_accommodation(
            name="Vineyard Inn",
            location="Sonoma",
            check_in_date="2026-02-14",
            nights=2,
            guests=2,
        )
        book_restaurant(
            restaurant_name="Della Santina's",
            date="2026-02-14",
            time="19:00",
            party_size=2,
        )

        store = BookingStore.get_instance()
        all_bookings = store.get_all_bookings()

        assert len(all_bookings) == 2


class TestTravelToolsRegistry:
    """Tests for TRAVEL_TOOLS registry."""

    def test_all_tools_registered(self):
        """Test all 9 travel tools are in the registry."""
        expected_tools = [
            "search_accommodations",
            "get_accommodation_details",
            "book_accommodation",
            "search_restaurants",
            "get_restaurant_details",
            "book_restaurant",
            "plan_route",
            "search_activities",
            "book_spa_service",
        ]

        for tool_name in expected_tools:
            assert tool_name in TRAVEL_TOOLS, f"Missing tool: {tool_name}"

    def test_all_tools_are_callable(self):
        """Test all registered tools are callable."""
        for tool_name, tool_func in TRAVEL_TOOLS.items():
            assert callable(tool_func), f"Tool not callable: {tool_name}"
