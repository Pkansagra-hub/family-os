"""
Travel Tools Implementation
===========================

Real tool implementations with mock external service responses.
These tools are used in the Anniversary Demo to handle:
- Accommodation search, details, and booking
- Restaurant search, details, and booking
- Route planning with scenic options
- Activity search
- Spa service booking

All tools return structured data that the LLM can use in responses.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class BookingStatus(Enum):
    """Status of a booking."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


@dataclass
class Accommodation:
    """Accommodation search result."""

    name: str
    location: str
    property_type: str
    price_per_night: float
    rating: float
    amenities: List[str]
    description: str
    availability: bool = True
    special_features: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "location": self.location,
            "property_type": self.property_type,
            "price_per_night": self.price_per_night,
            "rating": self.rating,
            "amenities": self.amenities,
            "description": self.description,
            "availability": self.availability,
            "special_features": self.special_features,
        }


@dataclass
class AccommodationDetails:
    """Detailed information about an accommodation."""

    name: str
    location: str
    description: str
    price_per_night: float
    rating: float
    reviews_count: int
    amenities: List[str]
    room_types: List[Dict[str, Any]]
    policies: Dict[str, str]
    contact: Dict[str, str]
    special_features: List[str]
    nearby_attractions: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "location": self.location,
            "description": self.description,
            "price_per_night": self.price_per_night,
            "rating": self.rating,
            "reviews_count": self.reviews_count,
            "amenities": self.amenities,
            "room_types": self.room_types,
            "policies": self.policies,
            "contact": self.contact,
            "special_features": self.special_features,
            "nearby_attractions": self.nearby_attractions,
        }


@dataclass
class BookingConfirmation:
    """Confirmation for a booking."""

    confirmation_number: str
    booking_type: str
    name: str
    date: str
    details: Dict[str, Any]
    status: BookingStatus = BookingStatus.CONFIRMED
    total_cost: Optional[float] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "confirmation_number": self.confirmation_number,
            "booking_type": self.booking_type,
            "name": self.name,
            "date": self.date,
            "details": self.details,
            "status": self.status.value,
            "total_cost": self.total_cost,
            "notes": self.notes,
        }


@dataclass
class Restaurant:
    """Restaurant search result."""

    name: str
    location: str
    cuisine: str
    price_range: str
    rating: float
    description: str
    dietary_accommodations: List[str]
    availability: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "location": self.location,
            "cuisine": self.cuisine,
            "price_range": self.price_range,
            "rating": self.rating,
            "description": self.description,
            "dietary_accommodations": self.dietary_accommodations,
            "availability": self.availability,
        }


@dataclass
class RestaurantDetails:
    """Detailed information about a restaurant."""

    name: str
    location: str
    cuisine: str
    description: str
    price_range: str
    rating: float
    reviews_count: int
    menu_highlights: List[str]
    dietary_options: List[str]
    birthday_specials: List[str]
    hours: Dict[str, str]
    contact: Dict[str, str]
    dress_code: str
    reservations_required: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "location": self.location,
            "cuisine": self.cuisine,
            "description": self.description,
            "price_range": self.price_range,
            "rating": self.rating,
            "reviews_count": self.reviews_count,
            "menu_highlights": self.menu_highlights,
            "dietary_options": self.dietary_options,
            "birthday_specials": self.birthday_specials,
            "hours": self.hours,
            "contact": self.contact,
            "dress_code": self.dress_code,
            "reservations_required": self.reservations_required,
        }


@dataclass
class Route:
    """Driving route result."""

    origin: str
    destination: str
    distance_miles: float
    duration_minutes: int
    route_type: str
    directions: List[str]
    highlights: List[str]
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "origin": self.origin,
            "destination": self.destination,
            "distance_miles": self.distance_miles,
            "duration_minutes": self.duration_minutes,
            "route_type": self.route_type,
            "directions": self.directions,
            "highlights": self.highlights,
            "warnings": self.warnings,
        }


@dataclass
class Activity:
    """Activity search result."""

    name: str
    location: str
    category: str
    duration: str
    price: float
    description: str
    rating: float
    availability: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "location": self.location,
            "category": self.category,
            "duration": self.duration,
            "price": self.price,
            "description": self.description,
            "rating": self.rating,
            "availability": self.availability,
        }


# =============================================================================
# MOCK DATA FOR ANNIVERSARY DEMO
# =============================================================================

# Sonoma accommodations
MOCK_ACCOMMODATIONS = {
    "sonoma": [
        Accommodation(
            name="Vineyard Inn",
            location="Sonoma",
            property_type="bnb",
            price_per_night=289.0,
            rating=4.8,
            amenities=["wifi", "pool", "spa", "breakfast", "vineyard_views"],
            description="Charming B&B nestled among rolling vineyards with stunning sunset views",
            special_features=["Complimentary wine tasting", "Private balconies", "In-room spa"],
        ),
        Accommodation(
            name="Sonoma Valley Lodge",
            location="Sonoma",
            property_type="hotel",
            price_per_night=225.0,
            rating=4.5,
            amenities=["wifi", "pool", "restaurant", "fitness_center"],
            description="Modern hotel in the heart of Sonoma Plaza",
            special_features=["Walking distance to tasting rooms", "Rooftop bar"],
        ),
        Accommodation(
            name="The Wine Country Cottage",
            location="Sonoma",
            property_type="vacation_rental",
            price_per_night=350.0,
            rating=4.9,
            amenities=["wifi", "full_kitchen", "hot_tub", "private_garden"],
            description="Secluded cottage with complete privacy and luxury",
            special_features=["Private hot tub", "Outdoor firepit", "Complimentary bikes"],
        ),
    ],
    "napa": [
        Accommodation(
            name="Napa Grand Hotel",
            location="Napa",
            property_type="hotel",
            price_per_night=310.0,
            rating=4.6,
            amenities=["wifi", "pool", "spa", "restaurant", "concierge"],
            description="Elegant hotel in downtown Napa with world-class amenities",
            special_features=["Michelin-star restaurant", "Full-service spa"],
        ),
    ],
}

MOCK_ACCOMMODATION_DETAILS = {
    "Vineyard Inn": AccommodationDetails(
        name="Vineyard Inn",
        location="Sonoma",
        description="The Vineyard Inn is a charming bed and breakfast nestled among the rolling vineyards of Sonoma Valley. Our property offers breathtaking views of the surrounding wine country, with each room featuring a private balcony overlooking our estate vineyard. We pride ourselves on personalized service and attention to detail.",
        price_per_night=289.0,
        rating=4.8,
        reviews_count=342,
        amenities=[
            "Free WiFi",
            "Heated Pool",
            "On-site Spa",
            "Gourmet Breakfast Included",
            "Wine Cellar",
            "Electric Car Charging",
            "Concierge Service",
        ],
        room_types=[
            {
                "name": "Vineyard View King",
                "price": 289,
                "features": ["King bed", "Vineyard view", "Private balcony"],
            },
            {
                "name": "Deluxe Suite",
                "price": 359,
                "features": ["King bed", "Living area", "Jacuzzi tub", "Panoramic view"],
            },
            {
                "name": "Romance Package",
                "price": 429,
                "features": ["Suite", "Champagne", "Couples massage", "Late checkout"],
            },
        ],
        policies={
            "check_in": "3:00 PM",
            "check_out": "11:00 AM",
            "cancellation": "Free cancellation up to 48 hours before check-in",
            "pets": "Not allowed",
        },
        contact={
            "phone": "(707) 555-0123",
            "email": "reservations@vineyardinn.com",
            "address": "1234 Vineyard Lane, Sonoma, CA 95476",
        },
        special_features=[
            "Complimentary wine tasting daily at 5 PM",
            "Partnerships with 12 local wineries for exclusive tastings",
            "In-room spa services available",
            "Gourmet breakfast featuring local ingredients",
        ],
        nearby_attractions=[
            "Sonoma Plaza (10 min walk)",
            "Buena Vista Winery (5 min drive)",
            "Gloria Ferrer Caves (15 min drive)",
            "Jack London State Historic Park (20 min drive)",
        ],
    ),
    "Sonoma Valley Lodge": AccommodationDetails(
        name="Sonoma Valley Lodge",
        location="Sonoma",
        description="Modern comfort meets wine country charm at Sonoma Valley Lodge.",
        price_per_night=225.0,
        rating=4.5,
        reviews_count=518,
        amenities=["Free WiFi", "Pool", "Restaurant", "Fitness Center"],
        room_types=[
            {"name": "Standard King", "price": 225, "features": ["King bed", "City view"]},
            {"name": "Deluxe Double", "price": 275, "features": ["Two queens", "Garden view"]},
        ],
        policies={
            "check_in": "4:00 PM",
            "check_out": "12:00 PM",
            "cancellation": "24 hours",
            "pets": "Allowed",
        },
        contact={
            "phone": "(707) 555-0456",
            "email": "info@sonomalodge.com",
            "address": "456 Main St, Sonoma, CA",
        },
        special_features=["Rooftop bar", "Walking distance to plaza"],
        nearby_attractions=["Sonoma Plaza", "Local tasting rooms"],
    ),
}

# Sonoma restaurants
MOCK_RESTAURANTS = {
    "sonoma": [
        Restaurant(
            name="Della Santina's",
            location="Sonoma",
            cuisine="Italian",
            price_range="$$$",
            rating=4.7,
            description="Authentic Tuscan cuisine in a romantic garden setting",
            dietary_accommodations=[
                "vegetarian",
                "gluten-free",
                "shellfish-free preparations available",
            ],
        ),
        Restaurant(
            name="The Girl & The Fig",
            location="Sonoma",
            cuisine="French-California",
            price_range="$$$",
            rating=4.6,
            description="Country French food with California flair on Sonoma Plaza",
            dietary_accommodations=["vegetarian", "vegan options", "allergen menu available"],
        ),
        Restaurant(
            name="LaSalette",
            location="Sonoma",
            cuisine="Portuguese",
            price_range="$$",
            rating=4.5,
            description="Portuguese cuisine with fresh local ingredients",
            dietary_accommodations=["gluten-free options", "pescatarian"],
        ),
    ],
}

MOCK_RESTAURANT_DETAILS = {
    "Della Santina's": RestaurantDetails(
        name="Della Santina's",
        location="133 E Napa St, Sonoma, CA 95476",
        cuisine="Italian/Tuscan",
        description="Family-owned since 1990, Della Santina's brings the flavors of Tuscany to Sonoma's historic plaza. Our recipes have been passed down through generations, featuring handmade pasta, wood-fired rotisserie, and the freshest local ingredients. The romantic garden patio is perfect for special celebrations.",
        price_range="$$$",
        rating=4.7,
        reviews_count=892,
        menu_highlights=[
            "Handmade Pappardelle with Wild Boar Ragu",
            "Wood-Fired Rotisserie Chicken",
            "Tiramisu (house specialty)",
            "Osso Buco with Saffron Risotto",
            "Fresh Burrata with Heirloom Tomatoes",
        ],
        dietary_options=[
            "Vegetarian pasta options",
            "Gluten-free pasta available",
            "Shellfish-free preparations (kitchen can accommodate)",
            "Dairy-free options",
        ],
        birthday_specials=[
            "Complimentary dessert with birthday message",
            "Personalized menu cards for celebrations",
            "Private garden alcove for special occasions (request in advance)",
            "Anniversary/birthday wine toast offered",
        ],
        hours={
            "Monday": "11:30 AM - 9:00 PM",
            "Tuesday": "11:30 AM - 9:00 PM",
            "Wednesday": "11:30 AM - 9:00 PM",
            "Thursday": "11:30 AM - 9:00 PM",
            "Friday": "11:30 AM - 10:00 PM",
            "Saturday": "11:30 AM - 10:00 PM",
            "Sunday": "11:30 AM - 9:00 PM",
        },
        contact={
            "phone": "(707) 935-0576",
            "email": "reservations@dellasantinas.com",
            "website": "www.dellasantinas.com",
        },
        dress_code="Smart casual",
        reservations_required=True,
    ),
    "The Girl & The Fig": RestaurantDetails(
        name="The Girl & The Fig",
        location="110 W Spain St, Sonoma, CA 95476",
        cuisine="French-California",
        description="A Sonoma institution celebrating country French cuisine with California wine country flair.",
        price_range="$$$",
        rating=4.6,
        reviews_count=1243,
        menu_highlights=[
            "Fig & Arugula Salad",
            "Duck Confit",
            "Steak Frites",
            "Lavender Creme Brulee",
        ],
        dietary_options=["Vegetarian", "Vegan", "Gluten-free"],
        birthday_specials=["Complimentary dessert", "Champagne toast available"],
        hours={"Daily": "11:00 AM - 10:00 PM"},
        contact={"phone": "(707) 938-3634"},
        dress_code="Casual",
        reservations_required=True,
    ),
}

# Mock routes
MOCK_ROUTES = {
    ("San Francisco", "Sonoma"): {
        "fastest": Route(
            origin="San Francisco",
            destination="Sonoma",
            distance_miles=45.2,
            duration_minutes=55,
            route_type="fastest",
            directions=[
                "Head north on US-101",
                "Take exit 460B for CA-37 toward Napa/Vallejo",
                "Continue on CA-121 N",
                "Turn right onto CA-12 W",
                "Arrive at Sonoma Plaza",
            ],
            highlights=["Quick highway route"],
            warnings=["Can be congested during rush hour"],
        ),
        "scenic": Route(
            origin="San Francisco",
            destination="Sonoma",
            distance_miles=52.8,
            duration_minutes=85,
            route_type="scenic",
            directions=[
                "Cross the Golden Gate Bridge on US-101 N",
                "Take exit for CA-1 N (Shoreline Highway)",
                "Continue through Stinson Beach",
                "Turn right onto CA-1/Shoreline Highway toward Point Reyes Station",
                "Turn right onto Petaluma-Point Reyes Rd",
                "Continue to CA-116 E through Petaluma",
                "Turn right onto CA-12 E toward Sonoma",
                "Arrive at Sonoma Plaza",
            ],
            highlights=[
                "Golden Gate Bridge views",
                "Stunning Pacific Ocean coastline",
                "Muir Woods nearby",
                "Charming town of Point Reyes Station",
                "Rolling hills of Marin County",
                "Pastoral Petaluma farmland",
            ],
            warnings=[
                "Winding roads - not recommended if prone to car sickness",
                "Add extra time on weekends (popular route)",
            ],
        ),
    },
}

# Mock activities
MOCK_ACTIVITIES = {
    "sonoma": [
        Activity(
            name="Wine Tasting at Gloria Ferrer",
            location="Sonoma",
            category="food_wine",
            duration="2-3 hours",
            price=45.0,
            description="Sparkling wine tasting with vineyard views",
            rating=4.8,
        ),
        Activity(
            name="Hot Air Balloon Ride",
            location="Sonoma",
            category="adventure",
            duration="3-4 hours",
            price=299.0,
            description="Sunrise balloon flight over wine country",
            rating=4.9,
        ),
        Activity(
            name="Couples Spa Day at Spa at Vineyard Inn",
            location="Vineyard Inn, Sonoma",
            category="relaxation",
            duration="2-3 hours",
            price=350.0,
            description="Full spa experience with couples massage, facials, and wine",
            rating=4.9,
        ),
        Activity(
            name="Sonoma Valley Bike Tour",
            location="Sonoma",
            category="nature",
            duration="half-day",
            price=89.0,
            description="Guided bike tour through vineyards with stops at tasting rooms",
            rating=4.7,
        ),
        Activity(
            name="Jack London State Park Hiking",
            location="Glen Ellen (near Sonoma)",
            category="nature",
            duration="2-4 hours",
            price=10.0,
            description="Beautiful trails through redwoods and historic ranch",
            rating=4.6,
        ),
    ],
    "vineyard inn": [
        Activity(
            name="Couples Massage",
            location="Vineyard Inn Spa",
            category="relaxation",
            duration="90 minutes",
            price=320.0,
            description="Side-by-side massage with aromatherapy and wine country views",
            rating=4.9,
        ),
        Activity(
            name="Wine & Wellness Package",
            location="Vineyard Inn Spa",
            category="relaxation",
            duration="3 hours",
            price=450.0,
            description="Massage, facial, and private wine tasting",
            rating=4.9,
        ),
        Activity(
            name="Morning Yoga in the Vineyard",
            location="Vineyard Inn",
            category="relaxation",
            duration="1 hour",
            price=25.0,
            description="Gentle yoga session among the vines",
            rating=4.7,
        ),
    ],
}

# Mock spa services
MOCK_SPA_SERVICES = {
    "Vineyard Inn": {
        "massage": {"name": "Swedish Massage", "duration": "60 min", "price": 150.0},
        "couples_massage": {
            "name": "Couples Relaxation Massage",
            "duration": "90 min",
            "price": 320.0,
        },
        "facial": {"name": "Wine Country Facial", "duration": "60 min", "price": 125.0},
        "body_treatment": {"name": "Grape Seed Body Wrap", "duration": "75 min", "price": 175.0},
        "package": {"name": "Romance Package", "duration": "3 hours", "price": 450.0},
    },
}


# =============================================================================
# BOOKING STORAGE (in-memory for demo)
# =============================================================================


class BookingStore:
    """In-memory storage for demo bookings."""

    _instance: Optional[BookingStore] = None

    def __init__(self):
        self._bookings: Dict[str, BookingConfirmation] = {}

    @classmethod
    def get_instance(cls) -> BookingStore:
        if cls._instance is None:
            cls._instance = BookingStore()
        return cls._instance

    def add_booking(self, booking: BookingConfirmation) -> None:
        self._bookings[booking.confirmation_number] = booking

    def get_booking(self, confirmation_number: str) -> Optional[BookingConfirmation]:
        return self._bookings.get(confirmation_number)

    def get_all_bookings(self) -> List[BookingConfirmation]:
        return list(self._bookings.values())

    def clear(self) -> None:
        self._bookings.clear()


def _generate_confirmation_number(prefix: str = "FOS") -> str:
    """Generate a unique confirmation number."""
    return f"{prefix}-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================


def search_accommodations(
    location: str,
    check_in_date: str,
    nights: int,
    party_size: int = 2,
    budget_per_night: Optional[float] = None,
    amenities: Optional[List[str]] = None,
    property_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Search for accommodations in a location.

    Returns a list of matching accommodations with pricing and availability.
    """
    location_key = location.lower()
    results = MOCK_ACCOMMODATIONS.get(location_key, [])

    # Filter by budget if specified
    if budget_per_night is not None:
        results = [a for a in results if a.price_per_night <= budget_per_night]

    # Filter by property type if specified
    if property_type and property_type != "any":
        results = [a for a in results if a.property_type == property_type]

    # Filter by amenities if specified
    if amenities:
        results = [a for a in results if all(am in a.amenities for am in amenities)]

    return {
        "success": True,
        "location": location,
        "check_in_date": check_in_date,
        "nights": nights,
        "party_size": party_size,
        "results_count": len(results),
        "results": [a.to_dict() for a in results],
        "search_params": {
            "budget_per_night": budget_per_night,
            "amenities": amenities,
            "property_type": property_type,
        },
    }


def get_accommodation_details(
    name: str,
    location: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get detailed information about a specific accommodation.

    Returns comprehensive details including room types, policies, and amenities.
    """
    details = MOCK_ACCOMMODATION_DETAILS.get(name)

    if details:
        return {
            "success": True,
            "details": details.to_dict(),
        }

    return {
        "success": False,
        "error": f"Accommodation '{name}' not found",
        "suggestions": list(MOCK_ACCOMMODATION_DETAILS.keys()),
    }


def book_accommodation(
    name: str,
    location: str,
    check_in_date: str,
    nights: int,
    guests: int,
    special_requests: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Book an accommodation.

    Creates a booking record and returns confirmation details.
    """
    details = MOCK_ACCOMMODATION_DETAILS.get(name)

    if not details:
        return {
            "success": False,
            "error": f"Accommodation '{name}' not found",
        }

    # Calculate total cost
    total_cost = details.price_per_night * nights

    # Create booking confirmation
    confirmation = BookingConfirmation(
        confirmation_number=_generate_confirmation_number("ACC"),
        booking_type="accommodation",
        name=name,
        date=check_in_date,
        details={
            "location": location,
            "check_in": check_in_date,
            "nights": nights,
            "guests": guests,
            "check_out": f"{nights} nights from {check_in_date}",
            "room_rate": details.price_per_night,
            "special_requests": special_requests or [],
        },
        total_cost=total_cost,
        notes=[
            f"Check-in: {details.policies.get('check_in', '3:00 PM')}",
            f"Check-out: {details.policies.get('check_out', '11:00 AM')}",
            "Confirmation email sent to your registered email",
        ],
    )

    # Store the booking
    BookingStore.get_instance().add_booking(confirmation)

    return {
        "success": True,
        "confirmation": confirmation.to_dict(),
        "message": f"Successfully booked {nights} nights at {name}",
    }


def search_restaurants(
    location: str,
    cuisine: Optional[str] = None,
    date: Optional[str] = None,
    time: Optional[str] = None,
    party_size: int = 2,
    avoid_ingredients: Optional[List[str]] = None,
    price_range: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Search for restaurants in a location.

    Supports filtering by cuisine, dietary restrictions, and price range.
    """
    location_key = location.lower()
    results = MOCK_RESTAURANTS.get(location_key, [])

    # Filter by cuisine if specified
    if cuisine:
        cuisine_lower = cuisine.lower()
        results = [r for r in results if cuisine_lower in r.cuisine.lower()]

    # Filter by price range if specified
    if price_range:
        results = [r for r in results if r.price_range == price_range]

    # Note dietary accommodations for allergies
    allergy_notes = []
    if avoid_ingredients:
        allergy_notes = [
            f"Note: Searched with dietary restriction for {', '.join(avoid_ingredients)}",
            "All results can accommodate these restrictions - please confirm when booking",
        ]

    return {
        "success": True,
        "location": location,
        "search_params": {
            "cuisine": cuisine,
            "date": date,
            "time": time,
            "party_size": party_size,
            "avoid_ingredients": avoid_ingredients,
            "price_range": price_range,
        },
        "results_count": len(results),
        "results": [r.to_dict() for r in results],
        "allergy_notes": allergy_notes,
    }


def get_restaurant_details(
    name: str,
    query: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get detailed information about a specific restaurant.

    Can optionally focus on specific information like birthday specials or menu.
    """
    details = MOCK_RESTAURANT_DETAILS.get(name)

    if not details:
        return {
            "success": False,
            "error": f"Restaurant '{name}' not found",
            "suggestions": list(MOCK_RESTAURANT_DETAILS.keys()),
        }

    result = {
        "success": True,
        "details": details.to_dict(),
    }

    # Add focused info if query specified
    if query:
        query_lower = query.lower()
        if "birthday" in query_lower:
            result["focused_info"] = {
                "type": "birthday_specials",
                "info": details.birthday_specials,
            }
        elif "menu" in query_lower:
            result["focused_info"] = {
                "type": "menu_highlights",
                "info": details.menu_highlights,
            }
        elif "dietary" in query_lower or "allergy" in query_lower:
            result["focused_info"] = {
                "type": "dietary_options",
                "info": details.dietary_options,
            }

    return result


def book_restaurant(
    restaurant_name: str,
    date: str,
    time: str,
    party_size: int,
    special_requests: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Make a restaurant reservation.

    Creates a booking record with any special requests.
    """
    details = MOCK_RESTAURANT_DETAILS.get(restaurant_name)

    if not details:
        return {
            "success": False,
            "error": f"Restaurant '{restaurant_name}' not found",
        }

    # Create booking confirmation
    confirmation = BookingConfirmation(
        confirmation_number=_generate_confirmation_number("RES"),
        booking_type="restaurant",
        name=restaurant_name,
        date=date,
        details={
            "time": time,
            "party_size": party_size,
            "location": details.location,
            "special_requests": special_requests or [],
        },
        notes=[
            f"Dress code: {details.dress_code}",
            "Please arrive 10 minutes before your reservation",
            "Confirmation text will be sent 24 hours before",
        ],
    )

    # Check for allergy notes in special requests
    if special_requests:
        for request in special_requests:
            if "allergy" in request.lower():
                confirmation.notes.append(
                    "ALLERGY NOTE: Kitchen has been notified of dietary restrictions"
                )
                break

    # Store the booking
    BookingStore.get_instance().add_booking(confirmation)

    return {
        "success": True,
        "confirmation": confirmation.to_dict(),
        "message": f"Successfully reserved table for {party_size} at {restaurant_name} on {date} at {time}",
    }


def plan_route(
    origin: str,
    destination: str,
    preference: str = "fastest",
    departure_time: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Plan a driving route between locations.

    Supports fastest and scenic route options.
    """
    route_key = (origin, destination)
    routes = MOCK_ROUTES.get(route_key)

    if not routes:
        # Check reverse route
        reverse_key = (destination, origin)
        routes = MOCK_ROUTES.get(reverse_key)
        if routes:
            # We'd need to reverse directions - for demo just use as-is
            pass
        else:
            # Generate generic route for unknown locations
            return {
                "success": True,
                "route": {
                    "origin": origin,
                    "destination": destination,
                    "distance_miles": 50.0,
                    "duration_minutes": 60,
                    "route_type": preference,
                    "directions": [
                        f"Head toward {destination}",
                        "Follow main roads",
                        f"Arrive at {destination}",
                    ],
                    "highlights": [],
                    "warnings": ["Route estimated - check maps for exact directions"],
                },
                "note": "Estimated route - specific directions not available in demo",
            }

    route = routes.get(preference, routes.get("fastest"))

    return {
        "success": True,
        "route": route.to_dict(),
        "departure_time": departure_time,
        "estimated_arrival": f"{route.duration_minutes} minutes from departure",
    }


def search_activities(
    location: str,
    date: Optional[str] = None,
    category: Optional[str] = None,
    duration: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Search for activities and things to do.

    Supports filtering by category and duration.
    """
    location_key = location.lower()
    results = MOCK_ACTIVITIES.get(location_key, [])

    # Also check for partial matches (e.g., "Vineyard Inn, Sonoma" -> "vineyard inn")
    if not results:
        for key in MOCK_ACTIVITIES:
            if key in location_key or location_key in key:
                results = MOCK_ACTIVITIES[key]
                break

    # Filter by category if specified
    if category:
        results = [a for a in results if a.category == category]

    # Filter by duration if specified
    if duration:
        results = [a for a in results if duration.lower() in a.duration.lower()]

    return {
        "success": True,
        "location": location,
        "search_params": {
            "date": date,
            "category": category,
            "duration": duration,
        },
        "results_count": len(results),
        "results": [a.to_dict() for a in results],
    }


def book_spa_service(
    location: str,
    service: str,
    date: str,
    time: str,
    guests: int = 1,
) -> Dict[str, Any]:
    """
    Book a spa service or treatment.

    Creates a booking record for spa appointments.
    """
    # Extract property name from location
    property_name = location
    for key in MOCK_SPA_SERVICES:
        if key.lower() in location.lower():
            property_name = key
            break

    services = MOCK_SPA_SERVICES.get(property_name)

    if not services:
        return {
            "success": False,
            "error": f"Spa services not available at '{location}'",
            "available_locations": list(MOCK_SPA_SERVICES.keys()),
        }

    service_info = services.get(service)

    if not service_info:
        return {
            "success": False,
            "error": f"Service '{service}' not available",
            "available_services": list(services.keys()),
        }

    # Calculate total cost
    total_cost = service_info["price"]
    if service == "couples_massage" or guests > 1:
        total_cost = service_info["price"]  # Already priced for couples

    # Create booking confirmation
    confirmation = BookingConfirmation(
        confirmation_number=_generate_confirmation_number("SPA"),
        booking_type="spa",
        name=service_info["name"],
        date=date,
        details={
            "location": property_name,
            "service": service,
            "service_name": service_info["name"],
            "duration": service_info["duration"],
            "time": time,
            "guests": guests,
        },
        total_cost=total_cost,
        notes=[
            "Please arrive 15 minutes before your appointment",
            "Robes and slippers provided",
            "Access to relaxation lounge included",
        ],
    )

    # Store the booking
    BookingStore.get_instance().add_booking(confirmation)

    return {
        "success": True,
        "confirmation": confirmation.to_dict(),
        "message": f"Successfully booked {service_info['name']} at {property_name} on {date} at {time}",
    }


# =============================================================================
# TOOL FUNCTION MAP (for easy lookup by name)
# =============================================================================

TRAVEL_TOOLS = {
    "search_accommodations": search_accommodations,
    "get_accommodation_details": get_accommodation_details,
    "book_accommodation": book_accommodation,
    "search_restaurants": search_restaurants,
    "get_restaurant_details": get_restaurant_details,
    "book_restaurant": book_restaurant,
    "plan_route": plan_route,
    "search_activities": search_activities,
    "book_spa_service": book_spa_service,
}


def execute_travel_tool(tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a travel tool by name with given parameters."""
    tool_func = TRAVEL_TOOLS.get(tool_name)

    if not tool_func:
        return {
            "success": False,
            "error": f"Unknown travel tool: {tool_name}",
            "available_tools": list(TRAVEL_TOOLS.keys()),
        }

    try:
        return tool_func(**params)
    except TypeError as e:
        return {
            "success": False,
            "error": f"Invalid parameters: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Tool execution failed: {e}",
        }
