"""
Response bank for canned (deterministic) tool responses.

Provides predictable, repeatable tool outputs for benchmarking.
Each tool has a response map keyed by argument values.
Some tools support sequence responses (different results on Nth call).

20 research topics for context-stress testing (Test 1).
Travel data for 5 cities (Tests 2-7). Error responses for recovery (Test 4).
Long-term facts for retention testing (Test 8).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Research topics (20 topics for Test 1: context stress)
# ---------------------------------------------------------------------------

RESEARCH_TOPICS: Dict[str, Dict[str, Any]] = {
    "quantum_computing": {
        "title": "Quantum Computing",
        "summary": "Quantum computing uses quantum bits (qubits) that can exist in superposition states. Key players include IBM (127-qubit Eagle), Google (Sycamore), and IonQ. Current applications: cryptography, drug discovery, optimization. Estimated market size: $65B by 2030.",
        "facts": {
            "technology": "qubits in superposition",
            "market_size_2030": "$65B",
            "key_player": "IBM",
            "top_qubit_count": 127,
        },
    },
    "crispr_gene_editing": {
        "title": "CRISPR Gene Editing",
        "summary": "CRISPR-Cas9 enables precise DNA editing. Nobel Prize 2020 to Doudna and Charpentier. Applications: sickle cell disease treatment (Casgevy approved 2023), crop improvement, malaria-resistant mosquitoes. Ethical concerns around germline editing persist.",
        "facts": {
            "nobel_year": 2020,
            "first_approved_therapy": "Casgevy",
            "disease_treated": "sickle cell",
            "inventor": "Doudna and Charpentier",
        },
    },
    "renewable_energy": {
        "title": "Renewable Energy Trends",
        "summary": "Solar capacity grew 26% in 2024. Wind power: 906 GW installed globally. Battery storage costs dropped 89% since 2010. Leading countries: China (largest solar), Denmark (highest wind share at 55%). Green hydrogen emerging as storage solution.",
        "facts": {
            "solar_growth_2024": "26%",
            "wind_installed_gw": 906,
            "battery_cost_drop": "89% since 2010",
            "top_solar_country": "China",
        },
    },
    "artificial_intelligence": {
        "title": "AI State of the Art",
        "summary": "Large language models dominate: GPT-4, Gemini 2.0, Claude 3.5. Multimodal AI processes text, images, video. AI regulation: EU AI Act (2024), US Executive Order. Key risks: hallucination, bias, job displacement. AGI timeline estimates: 2030-2060.",
        "facts": {
            "top_models": "GPT-4, Gemini 2.0, Claude 3.5",
            "regulation": "EU AI Act 2024",
            "agi_estimate": "2030-2060",
        },
    },
    "space_exploration": {
        "title": "Space Exploration",
        "summary": "Artemis III planned for 2026 (Moon landing). SpaceX Starship: largest rocket ever built, 150t to LEO. Mars missions: NASA Perseverance collecting samples. James Webb Telescope: discovered earliest galaxies (13.4B years old). Space tourism: Blue Origin, Virgin Galactic.",
        "facts": {
            "artemis_iii_year": 2026,
            "starship_payload_leo": "150 tons",
            "jwst_oldest_galaxy": "13.4B years",
            "mars_rover": "Perseverance",
        },
    },
    "blockchain_defi": {
        "title": "Blockchain and DeFi",
        "summary": "Ethereum transitioned to Proof-of-Stake (2022), reducing energy 99.95%. DeFi TVL: $90B. Layer 2 solutions (Arbitrum, Optimism) reduce fees. CBDCs: 130 countries exploring. Bitcoin ETFs approved Jan 2024. NFT market contracted 80% from peak.",
        "facts": {
            "eth_energy_reduction": "99.95%",
            "defi_tvl": "$90B",
            "bitcoin_etf_year": 2024,
            "cbdc_countries": 130,
        },
    },
    "climate_change": {
        "title": "Climate Change Data",
        "summary": "Global temp +1.2C above pre-industrial. CO2: 424 ppm (2024). Ice loss: 150B tons/year from Antarctica. Sea level rise: 3.7mm/year. Tipping points: Amazon dieback, permafrost thaw, AMOC slowdown. Paris Agreement target: 1.5C increasingly unlikely.",
        "facts": {
            "temp_rise": "+1.2C",
            "co2_ppm": 424,
            "sea_level_rise_mm_yr": 3.7,
            "paris_target": "1.5C",
        },
    },
    "neuroscience": {
        "title": "Neuroscience Advances",
        "summary": "Brain-computer interfaces: Neuralink N1 implant (2024). Connectome mapping: C. elegans complete, mouse partial. Alzheimer's: lecanemab approved, reduces decline 27%. Consciousness theories: IIT vs Global Workspace. Sleep research: glymphatic system clears toxins.",
        "facts": {
            "bci_company": "Neuralink",
            "alzheimers_drug": "lecanemab",
            "efficacy": "27% reduction",
            "brain_cleanup": "glymphatic system",
        },
    },
    "electric_vehicles": {
        "title": "Electric Vehicle Market",
        "summary": "Global EV sales: 14.2M in 2024 (18% of market). Tesla leads but BYD closing gap. Battery tech: solid-state batteries expected 2027. Charging: 500k+ public chargers in US. Range leaders: Mercedes EQS (453mi), Lucid Air (516mi). Average price dropping toward parity with ICE.",
        "facts": {
            "ev_sales_2024": "14.2M",
            "market_share": "18%",
            "top_range": "Lucid Air 516mi",
            "solid_state_eta": 2027,
        },
    },
    "biotechnology": {
        "title": "Biotechnology Trends",
        "summary": "mRNA platform expanded beyond COVID: flu, RSV, cancer vaccines. Synthetic biology: engineered microbes produce insulin, spider silk. Lab-grown meat: Singapore, Israel approved. Longevity research: rapamycin, senolytics in clinical trials. Gene therapy costs: $1-3.5M per treatment.",
        "facts": {
            "mrna_expansion": "flu, RSV, cancer",
            "lab_meat_countries": "Singapore, Israel",
            "gene_therapy_cost": "$1-3.5M",
        },
    },
    "cybersecurity": {
        "title": "Cybersecurity Landscape",
        "summary": "Ransomware payments: $1.1B in 2023. Zero-trust architecture adopted by 60% of enterprises. AI-powered attacks increasing 300% YoY. Quantum threat: RSA-2048 breakable by ~2035. Post-quantum cryptography: NIST standards finalized 2024. Skills gap: 3.5M unfilled positions globally.",
        "facts": {
            "ransomware_2023": "$1.1B",
            "zero_trust_adoption": "60%",
            "quantum_threat_year": 2035,
            "skills_gap": "3.5M",
        },
    },
    "ocean_exploration": {
        "title": "Ocean Exploration",
        "summary": "Only 20% of ocean floor mapped in detail. Mariana Trench: 10,935m deep. Deep-sea mining: polymetallic nodules, controversial. Biodiversity: 2,000+ new species discovered per year. Coral bleaching: 75% of reefs affected. Plastic pollution: 8M tons enter oceans annually.",
        "facts": {
            "mapped_pct": "20%",
            "deepest_point_m": 10935,
            "new_species_yr": "2000+",
            "plastic_tons_yr": "8M",
        },
    },
    "fusion_energy": {
        "title": "Nuclear Fusion Progress",
        "summary": "NIF achieved ignition Dec 2022 (3.15 MJ out, 2.05 MJ in). ITER: 70% complete, first plasma ~2028. Private fusion: 40+ companies, $6B invested. Commonwealth Fusion Systems: SPARC tokamak targeting 2027. Key challenge: sustaining plasma, tritium breeding.",
        "facts": {
            "nif_output_mj": 3.15,
            "iter_completion": "70%",
            "private_investment": "$6B",
            "sparc_target": 2027,
        },
    },
    "autonomous_vehicles": {
        "title": "Autonomous Vehicles",
        "summary": "Waymo: 100k+ paid rides/week in SF, Phoenix, LA. Cruise suspended operations 2023. Tesla FSD: Level 2+ only. Regulation: varies by state. Trucking: Aurora, TuSimple piloting highway routes. Lidar vs camera debate ongoing. Insurance implications still unresolved.",
        "facts": {
            "waymo_rides_weekly": "100k+",
            "tesla_level": "Level 2+",
            "trucking_leaders": "Aurora, TuSimple",
        },
    },
    "mental_health_tech": {
        "title": "Mental Health Technology",
        "summary": "Digital therapeutics: Woebot, Wysa (AI chatbots). Psychedelic therapy: psilocybin FDA breakthrough status, MDMA Phase 3. Teletherapy grew 38x since 2019. VR exposure therapy for PTSD. Brain stimulation: TMS for depression (70% response rate). Global mental health market: $537B.",
        "facts": {
            "ai_therapy_apps": "Woebot, Wysa",
            "psilocybin_status": "FDA breakthrough",
            "tms_response_rate": "70%",
            "market_size": "$537B",
        },
    },
    "food_technology": {
        "title": "Food Technology",
        "summary": "Vertical farming market: $12B by 2028. Precision fermentation: producing dairy proteins without cows. Insect protein: approved in EU since 2023. Food waste tech: Too Good To Go saved 300M meals. Smart agriculture: drones, AI yield prediction, satellite monitoring.",
        "facts": {
            "vertical_farming_market": "$12B by 2028",
            "insect_protein_eu": 2023,
            "meals_saved": "300M",
        },
    },
    "materials_science": {
        "title": "Advanced Materials",
        "summary": "Graphene: commercialized for batteries, coatings. Metamaterials: invisibility cloaking at microwave frequencies. Self-healing concrete: bacteria-based, 30% longer lifespan. Aerogels: best insulator known (0.015 W/mK). Programmable matter: shape-shifting robots demonstrated at MIT.",
        "facts": {
            "graphene_uses": "batteries, coatings",
            "self_healing_lifespan": "30% longer",
            "aerogel_conductivity": "0.015 W/mK",
        },
    },
    "digital_twins": {
        "title": "Digital Twin Technology",
        "summary": "Market: $73B by 2027. Applications: manufacturing (predictive maintenance), healthcare (patient twins), urban planning (Singapore's Virtual Singapore). NASA uses digital twins for mission planning. Key platforms: Azure Digital Twins, NVIDIA Omniverse. Reduces downtime by 30-50%.",
        "facts": {
            "market_2027": "$73B",
            "downtime_reduction": "30-50%",
            "platforms": "Azure Digital Twins, NVIDIA Omniverse",
        },
    },
    "edge_computing": {
        "title": "Edge Computing",
        "summary": "Edge market: $61B in 2024. Latency: <10ms vs 50-100ms cloud. Use cases: autonomous vehicles, AR/VR, industrial IoT. 5G enables: network slicing for edge. AWS Wavelength, Azure Edge Zones. By 2025: 75% of enterprise data processed at edge. Energy concern: distributed cooling.",
        "facts": {"market_2024": "$61B", "latency": "<10ms", "enterprise_edge_2025": "75%"},
    },
    "synthetic_biology": {
        "title": "Synthetic Biology",
        "summary": "Market: $30B by 2026. Ginkgo Bioworks: largest cell programming foundry. Applications: bio-manufacturing, biofuels, fragrances, medicine. DNA data storage: 1 exabyte per gram theoretically. Minimal genome: Craig Venter's JCVI-syn3.0 (473 genes). Biosecurity: dual-use concerns.",
        "facts": {
            "market_2026": "$30B",
            "dna_storage": "1 EB/gram",
            "minimal_genome_genes": 473,
            "top_company": "Ginkgo Bioworks",
        },
    },
}


# ---------------------------------------------------------------------------
# Weather data (5 cities)
# ---------------------------------------------------------------------------

WEATHER_DATA: Dict[str, Dict[str, Any]] = {
    "paris": {
        "city": "Paris",
        "country": "France",
        "temp_c": 22,
        "condition": "Partly Cloudy",
        "humidity": 65,
        "wind_kph": 12,
    },
    "tokyo": {
        "city": "Tokyo",
        "country": "Japan",
        "temp_c": 28,
        "condition": "Sunny",
        "humidity": 70,
        "wind_kph": 8,
    },
    "new_york": {
        "city": "New York",
        "country": "USA",
        "temp_c": 18,
        "condition": "Overcast",
        "humidity": 55,
        "wind_kph": 15,
    },
    "london": {
        "city": "London",
        "country": "UK",
        "temp_c": 15,
        "condition": "Rainy",
        "humidity": 80,
        "wind_kph": 20,
    },
    "sydney": {
        "city": "Sydney",
        "country": "Australia",
        "temp_c": 25,
        "condition": "Sunny",
        "humidity": 45,
        "wind_kph": 10,
    },
    "berlin": {
        "city": "Berlin",
        "country": "Germany",
        "temp_c": 19,
        "condition": "Cloudy",
        "humidity": 60,
        "wind_kph": 14,
    },
    "mumbai": {
        "city": "Mumbai",
        "country": "India",
        "temp_c": 32,
        "condition": "Humid",
        "humidity": 85,
        "wind_kph": 6,
    },
    "san_francisco": {
        "city": "San Francisco",
        "country": "USA",
        "temp_c": 16,
        "condition": "Foggy",
        "humidity": 75,
        "wind_kph": 18,
    },
}


# ---------------------------------------------------------------------------
# Flight data
# ---------------------------------------------------------------------------

FLIGHT_DATA: Dict[str, List[Dict[str, Any]]] = {
    "sfo_jfk": [
        {
            "airline": "United",
            "flight": "UA100",
            "departure": "08:00",
            "arrival": "16:30",
            "price": 350,
            "stops": 0,
        },
        {
            "airline": "Delta",
            "flight": "DL200",
            "departure": "10:15",
            "arrival": "18:45",
            "price": 280,
            "stops": 0,
        },
        {
            "airline": "American",
            "flight": "AA300",
            "departure": "14:00",
            "arrival": "22:30",
            "price": 310,
            "stops": 1,
        },
    ],
    "jfk_lhr": [
        {
            "airline": "British Airways",
            "flight": "BA178",
            "departure": "19:00",
            "arrival": "07:00+1",
            "price": 650,
            "stops": 0,
        },
        {
            "airline": "Virgin Atlantic",
            "flight": "VS4",
            "departure": "21:30",
            "arrival": "09:30+1",
            "price": 580,
            "stops": 0,
        },
    ],
    "lhr_cdg": [
        {
            "airline": "Air France",
            "flight": "AF1681",
            "departure": "09:00",
            "arrival": "11:15",
            "price": 120,
            "stops": 0,
        },
        {
            "airline": "EasyJet",
            "flight": "U2814",
            "departure": "12:30",
            "arrival": "14:45",
            "price": 65,
            "stops": 0,
        },
    ],
    "cdg_nrt": [
        {
            "airline": "Air France",
            "flight": "AF276",
            "departure": "13:00",
            "arrival": "08:00+1",
            "price": 890,
            "stops": 0,
        },
        {
            "airline": "JAL",
            "flight": "JL46",
            "departure": "11:30",
            "arrival": "06:30+1",
            "price": 920,
            "stops": 0,
        },
    ],
    "sfo_syd": [
        {
            "airline": "Qantas",
            "flight": "QF74",
            "departure": "22:30",
            "arrival": "08:00+2",
            "price": 1200,
            "stops": 0,
        },
        {
            "airline": "United",
            "flight": "UA870",
            "departure": "11:00",
            "arrival": "19:00+1",
            "price": 980,
            "stops": 1,
        },
    ],
}


# ---------------------------------------------------------------------------
# Hotel data
# ---------------------------------------------------------------------------

HOTEL_DATA: Dict[str, List[Dict[str, Any]]] = {
    "paris": [
        {
            "name": "Hotel Le Marais",
            "stars": 4,
            "price_night": 180,
            "rating": 4.5,
            "amenities": ["wifi", "breakfast", "gym"],
        },
        {
            "name": "Budget Inn Paris",
            "stars": 2,
            "price_night": 65,
            "rating": 3.2,
            "amenities": ["wifi"],
        },
    ],
    "tokyo": [
        {
            "name": "Shinjuku Grand",
            "stars": 5,
            "price_night": 250,
            "rating": 4.8,
            "amenities": ["wifi", "spa", "restaurant", "gym"],
        },
        {
            "name": "Capsule Hotel Shibuya",
            "stars": 2,
            "price_night": 35,
            "rating": 3.8,
            "amenities": ["wifi", "locker"],
        },
    ],
    "london": [
        {
            "name": "The Savoy",
            "stars": 5,
            "price_night": 450,
            "rating": 4.9,
            "amenities": ["wifi", "spa", "restaurant", "bar", "gym"],
        },
        {
            "name": "Premier Inn Westminster",
            "stars": 3,
            "price_night": 95,
            "rating": 4.0,
            "amenities": ["wifi", "breakfast"],
        },
    ],
    "new_york": [
        {
            "name": "The Plaza",
            "stars": 5,
            "price_night": 550,
            "rating": 4.7,
            "amenities": ["wifi", "spa", "restaurant", "concierge"],
        },
        {
            "name": "Pod 51",
            "stars": 3,
            "price_night": 120,
            "rating": 4.1,
            "amenities": ["wifi", "rooftop"],
        },
    ],
    "sydney": [
        {
            "name": "Park Hyatt Sydney",
            "stars": 5,
            "price_night": 380,
            "rating": 4.8,
            "amenities": ["wifi", "pool", "spa", "restaurant"],
        },
        {
            "name": "YHA Sydney",
            "stars": 2,
            "price_night": 45,
            "rating": 3.9,
            "amenities": ["wifi", "kitchen"],
        },
    ],
}


# ---------------------------------------------------------------------------
# Database query results
# ---------------------------------------------------------------------------

DATABASE_RESULTS: Dict[str, Any] = {
    "user_preferences": {
        "preferred_airline": "United",
        "seat": "aisle",
        "meal": "vegetarian",
        "no_red_eye": True,
    },
    "booking_history": [
        {"id": "BK001", "route": "SFO-JFK", "date": "2024-06-15", "price": 320},
        {"id": "BK002", "route": "JFK-LHR", "date": "2024-08-20", "price": 680},
    ],
    "travel_budget": {"total": 5000, "spent": 1200, "remaining": 3800},
    "loyalty_programs": {"united_miles": 45000, "marriott_points": 120000, "status": "Gold"},
}


# ---------------------------------------------------------------------------
# API endpoint results
# ---------------------------------------------------------------------------

API_RESULTS: Dict[str, Any] = {
    "exchange_rates": {
        "USD_EUR": 0.92,
        "USD_GBP": 0.79,
        "USD_JPY": 149.5,
        "USD_AUD": 1.53,
        "timestamp": "2025-01-15",
    },
    "travel_advisories": {
        "france": {"level": 1, "message": "Exercise normal precautions"},
        "japan": {"level": 1, "message": "Exercise normal precautions"},
        "uk": {"level": 2, "message": "Exercise increased caution"},
    },
    "visa_requirements": {
        "us_to_france": "No visa needed for stays under 90 days",
        "us_to_japan": "No visa needed for stays under 90 days",
        "us_to_uk": "No visa needed for stays under 6 months",
    },
}


# ---------------------------------------------------------------------------
# Calculation results
# ---------------------------------------------------------------------------

CALCULATION_RESULTS: Dict[str, Any] = {
    "350 + 280 + 310": 940,
    "350 * 2": 700,
    "(350 + 180) * 5": 2650,
    "5000 - 1200 - 350 - 180": 3270,
    "14.2 * 0.18": 2.556,
}


# ---------------------------------------------------------------------------
# Flaky API responses (for error/recovery testing)
# ---------------------------------------------------------------------------


class FlakyCounter:
    """Tracks call counts per endpoint for deterministic failures."""

    def __init__(self):
        self.counts: Dict[str, int] = {}

    def get_count(self, endpoint: str) -> int:
        self.counts[endpoint] = self.counts.get(endpoint, 0) + 1
        return self.counts[endpoint]

    def reset(self):
        self.counts.clear()


FLAKY_COUNTER = FlakyCounter()


FLAKY_API_SCHEDULE: Dict[str, Dict[str, Any]] = {
    # Endpoint -> list of (call_number, response) pairs
    # If call number matches, return that response. Otherwise return success.
    "premium_flight_search": {
        "fail_on": [1, 2],  # First two calls fail
        "error": {
            "ok": False,
            "error_code": "RATE_LIMITED",
            "message": "API rate limit exceeded, try again later",
        },
        "success": {
            "ok": True,
            "output": {
                "airline": "Premium Air",
                "flight": "PA999",
                "price": 450,
                "class": "business",
            },
        },
    },
    "hotel_availability": {
        "fail_on": [1],
        "error": {
            "ok": False,
            "error_code": "SERVICE_UNAVAILABLE",
            "message": "Hotel booking service temporarily down",
        },
        "success": {"ok": True, "output": {"available": True, "rooms": 3, "price": 200}},
    },
    "weather_premium": {
        "fail_on": [1, 2, 3],  # Persistently fails
        "error": {"ok": False, "error_code": "AUTH_FAILED", "message": "API key expired"},
        "success": {"ok": True, "output": {"temp": 25, "forecast": "sunny"}},
    },
}


def get_flaky_response(endpoint: str) -> Dict[str, Any]:
    """Get response from flaky API based on call count."""
    schedule = FLAKY_API_SCHEDULE.get(endpoint, {})
    if not schedule:
        return {"ok": False, "error_code": "NOT_FOUND", "message": f"Unknown endpoint: {endpoint}"}

    call_num = FLAKY_COUNTER.get_count(endpoint)
    if call_num in schedule.get("fail_on", []):
        return schedule["error"]
    return schedule["success"]


# ---------------------------------------------------------------------------
# Large payload datasets (Test 9: 2,000-5,000 token tool outputs)
# ---------------------------------------------------------------------------


def _generate_customer_history() -> Dict[str, Any]:
    """Generate a ~3,500 token customer history dataset (200 records)."""
    customers = []
    product_names = [
        "Wireless Headphones",
        "Smart Watch",
        "USB-C Hub",
        "Laptop Stand",
        "Webcam HD",
        "Mechanical Keyboard",
        "Monitor Arm",
        "Desk Lamp LED",
        "Ergonomic Chair",
        "Standing Desk Mat",
        "Cable Organizer",
        "Mouse Pad XL",
        "Phone Charger 65W",
        "Bluetooth Speaker",
        "External SSD 1TB",
        "Noise Cancelling Earbuds",
        "Tablet Stylus",
        "HDMI Adapter",
        "Portable Battery Pack",
        "Ring Light",
    ]
    categories = ["Electronics", "Office", "Accessories", "Audio", "Storage"]
    regions = ["North America", "Europe", "Asia Pacific", "Latin America", "Middle East"]
    statuses = ["active", "inactive", "churned", "vip"]

    for i in range(200):
        cid = 10000 + i
        prod_idx = i % len(product_names)
        cat_idx = i % len(categories)
        region_idx = i % len(regions)
        status_idx = i % len(statuses)
        base_price = 19.99 + (i * 7.33) % 480
        qty = 1 + (i * 3) % 12
        customers.append(
            {
                "customer_id": f"CUST-{cid}",
                "name": f"Customer_{cid}",
                "email": f"user{cid}@example.com",
                "region": regions[region_idx],
                "status": statuses[status_idx],
                "lifetime_value": round(base_price * qty * 1.15, 2),
                "join_date": f"20{20 + (i % 5):02d}-{1 + (i % 12):02d}-{1 + (i % 28):02d}",
                "last_purchase": f"2025-{1 + (i % 12):02d}-{1 + (i % 28):02d}",
                "total_orders": 1 + (i * 2) % 45,
                "product": product_names[prod_idx],
                "category": categories[cat_idx],
                "unit_price": round(base_price, 2),
                "quantity": qty,
                "satisfaction_score": round(3.0 + (i % 20) * 0.1, 1),
                "referred_by": f"CUST-{10000 + (i + 50) % 200}" if i % 3 == 0 else None,
            }
        )

    return {
        "query": "customer_history_5years",
        "record_count": 200,
        "date_range": {"start": "2020-01-01", "end": "2025-12-31"},
        "summary_stats": {
            "total_revenue": 2_847_391.50,
            "avg_order_value": 142.37,
            "median_satisfaction": 4.1,
            "churn_rate_pct": 12.3,
            "vip_count": 50,
            "active_count": 50,
            "repeat_purchase_rate_pct": 67.8,
            "top_region": "North America",
            "top_category": "Electronics",
            "avg_lifetime_value": 14236.96,
        },
        "customers": customers,
    }


def _generate_analytics_report() -> Dict[str, Any]:
    """Generate a ~4,200 token analytics report."""
    segments = []
    segment_names = [
        "Power Buyers",
        "Casual Browsers",
        "Deal Seekers",
        "Brand Loyal",
        "New Adopters",
        "Returning Dormant",
        "High-Value Enterprise",
        "Small Business",
        "Student Discount",
        "Seasonal Shoppers",
    ]
    for i, name in enumerate(segment_names):
        segments.append(
            {
                "segment_id": f"SEG-{i+1:03d}",
                "name": name,
                "customer_count": 500 + i * 237,
                "avg_revenue_per_customer": round(120.0 + i * 45.7, 2),
                "conversion_rate_pct": round(2.1 + i * 0.8, 1),
                "avg_session_duration_min": round(3.5 + i * 1.2, 1),
                "bounce_rate_pct": round(45.0 - i * 3.2, 1),
                "retention_90day_pct": round(30.0 + i * 5.5, 1),
                "preferred_channel": ["web", "mobile", "email", "social", "search"][i % 5],
                "peak_hour": f"{8 + i}:00",
                "top_product_category": [
                    "Electronics",
                    "Office",
                    "Accessories",
                    "Audio",
                    "Storage",
                ][i % 5],
            }
        )

    monthly_trends = []
    for month_num in range(1, 13):
        monthly_trends.append(
            {
                "month": f"2025-{month_num:02d}",
                "revenue": round(180_000 + month_num * 15_000 + (month_num % 3) * 25_000, 2),
                "orders": 1200 + month_num * 100 + (month_num % 4) * 50,
                "new_customers": 300 + month_num * 20,
                "returning_customers": 800 + month_num * 60,
                "avg_order_value": round(140 + month_num * 2.5, 2),
                "refund_rate_pct": round(3.5 - month_num * 0.1, 1),
                "support_tickets": 150 + month_num * 10,
                "nps_score": round(45 + month_num * 1.5, 1),
            }
        )

    purchase_patterns = []
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for day in days:
        idx = days.index(day)
        purchase_patterns.append(
            {
                "day": day,
                "order_count": 150 + idx * 30 + (50 if idx >= 5 else 0),
                "avg_basket_size": round(3.2 + idx * 0.3, 1),
                "peak_hours": [f"{10+idx}:00", f"{14+idx}:00"],
                "mobile_pct": round(35 + idx * 5, 1),
                "desktop_pct": round(65 - idx * 5, 1),
            }
        )

    cohort_analysis = []
    for q in range(1, 9):
        year = 2024 if q <= 4 else 2025
        quarter = q if q <= 4 else q - 4
        cohort_analysis.append(
            {
                "cohort": f"Q{quarter}-{year}",
                "initial_size": 500 + q * 50,
                "month_1_retention_pct": round(80 - q * 1.5, 1),
                "month_3_retention_pct": round(55 - q * 2.0, 1),
                "month_6_retention_pct": round(35 - q * 1.0, 1),
                "avg_revenue_per_user": round(200 + q * 15, 2),
                "payback_period_months": round(2.5 + q * 0.2, 1),
            }
        )

    return {
        "report_id": "AR-2025-Q4-001",
        "generated_at": "2025-12-15T14:30:00Z",
        "report_type": "Comprehensive Purchase Analytics",
        "period": {"start": "2024-01-01", "end": "2025-12-31"},
        "executive_summary": {
            "total_revenue": 4_125_890.00,
            "yoy_growth_pct": 23.4,
            "total_customers": 12_450,
            "new_customer_growth_pct": 18.7,
            "avg_ltv": 331.40,
            "cac": 45.20,
            "ltv_cac_ratio": 7.33,
            "best_performing_segment": "Power Buyers",
            "highest_growth_segment": "New Adopters",
            "top_recommendation": "Invest in mobile experience -- mobile conversion up 34% YoY",
        },
        "segments": segments,
        "monthly_trends": monthly_trends,
        "purchase_patterns": purchase_patterns,
        "cohort_analysis": cohort_analysis,
        "risk_factors": [
            {
                "risk": "Churn rate increasing in 'Casual Browsers'",
                "severity": "medium",
                "impact_revenue": 120_000,
            },
            {
                "risk": "Supply chain delays for Electronics category",
                "severity": "high",
                "impact_revenue": 340_000,
            },
            {
                "risk": "Competitor pricing pressure in Audio segment",
                "severity": "low",
                "impact_revenue": 85_000,
            },
        ],
        "recommendations": [
            "Launch loyalty program targeting 'Deal Seekers' segment",
            "Optimize mobile checkout flow -- 23% cart abandonment on mobile",
            "Expand 'High-Value Enterprise' segment with dedicated account managers",
            "Implement predictive churn model for 'Returning Dormant' segment",
            "A/B test pricing in 'Student Discount' segment -- room for 8% increase",
        ],
    }


def _generate_vector_search_results() -> Dict[str, Any]:
    """Generate ~2,800 tokens of vector similarity search results (100 items)."""
    items = []
    base_titles = [
        "Machine Learning Fundamentals",
        "Deep Neural Networks",
        "NLP with Transformers",
        "Computer Vision Techniques",
        "Reinforcement Learning Guide",
        "GANs Explained",
        "Bayesian Statistics for ML",
        "Feature Engineering Best Practices",
        "Model Deployment at Scale",
        "AutoML and Neural Architecture Search",
        "Federated Learning Privacy",
        "Edge AI Deployment",
        "MLOps Pipeline Design",
        "Explainable AI Methods",
        "Time Series Forecasting",
        "Anomaly Detection Systems",
        "Recommendation Engines",
        "Knowledge Graph Construction",
        "Multi-Modal AI",
        "AI Ethics and Governance",
    ]
    tags_pool = [
        "machine-learning",
        "deep-learning",
        "nlp",
        "computer-vision",
        "reinforcement-learning",
        "statistics",
        "deployment",
        "mlops",
        "privacy",
        "edge-computing",
        "explainability",
        "time-series",
        "recommendations",
        "knowledge-graphs",
        "multi-modal",
        "ethics",
        "transformers",
        "optimization",
        "data-engineering",
        "evaluation",
    ]
    authors = [
        "Dr. Chen Wei",
        "Prof. Sarah Martinez",
        "Dr. Raj Patel",
        "Dr. Emma Thompson",
        "Prof. Yuki Tanaka",
        "Dr. Alex Petrov",
        "Prof. Maria Silva",
        "Dr. James O'Brien",
        "Dr. Aisha Khan",
        "Prof. Lars Eriksson",
    ]

    for i in range(100):
        title_idx = i % len(base_titles)
        variant = i // len(base_titles) + 1
        similarity = round(0.99 - i * 0.007, 4)
        items.append(
            {
                "id": f"DOC-{i+1:04d}",
                "title": (
                    f"{base_titles[title_idx]} (Vol. {variant})"
                    if variant > 1
                    else base_titles[title_idx]
                ),
                "author": authors[i % len(authors)],
                "similarity_score": max(similarity, 0.15),
                "publication_year": 2020 + (i % 6),
                "citations": 50 + i * 7,
                "abstract_snippet": f"This paper explores {base_titles[title_idx].lower()} with novel approaches to {tags_pool[i % len(tags_pool)]} and {tags_pool[(i+3) % len(tags_pool)]}. Results show {round(85 + (i % 15) * 0.5, 1)}% improvement over baseline.",
                "tags": [
                    tags_pool[i % len(tags_pool)],
                    tags_pool[(i + 5) % len(tags_pool)],
                    tags_pool[(i + 10) % len(tags_pool)],
                ],
                "relevance_rank": i + 1,
            }
        )

    return {
        "query_embedding_dim": 768,
        "index_size": 1_250_000,
        "search_time_ms": 23,
        "total_results": 100,
        "top_k": 100,
        "results": items,
        "cluster_summary": {
            "num_clusters": 8,
            "dominant_cluster": "deep-learning",
            "cluster_distribution": {
                "deep-learning": 28,
                "nlp": 18,
                "mlops": 15,
                "computer-vision": 12,
                "reinforcement-learning": 10,
                "privacy": 7,
                "ethics": 5,
                "other": 5,
            },
        },
        "metadata": {
            "embedding_model": "text-embedding-3-large",
            "distance_metric": "cosine",
            "index_type": "HNSW",
            "ef_search": 128,
        },
    }


# Pre-generate large datasets (computed once at import)
LARGE_CUSTOMER_HISTORY: Dict[str, Any] = _generate_customer_history()
LARGE_ANALYTICS_REPORT: Dict[str, Any] = _generate_analytics_report()
LARGE_VECTOR_SEARCH: Dict[str, Any] = _generate_vector_search_results()


def get_large_dataset(dataset_name: str) -> Dict[str, Any]:
    """Return one of the pre-generated large datasets by name."""
    datasets = {
        "customer_history": LARGE_CUSTOMER_HISTORY,
        "customer_history_5years": LARGE_CUSTOMER_HISTORY,
        "analytics_report": LARGE_ANALYTICS_REPORT,
        "purchase_analytics": LARGE_ANALYTICS_REPORT,
        "purchase_patterns": LARGE_ANALYTICS_REPORT,
        "vector_search": LARGE_VECTOR_SEARCH,
        "similar_items": LARGE_VECTOR_SEARCH,
        "document_search": LARGE_VECTOR_SEARCH,
    }
    name_lower = dataset_name.lower().replace(" ", "_").replace("-", "_")
    for key, data in datasets.items():
        if key in name_lower or name_lower in key:
            return data
    return {"error": f"Unknown large dataset: {dataset_name}", "available": list(datasets.keys())}


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def get_research_result(topic: str) -> Optional[Dict[str, Any]]:
    """Look up a research topic by key or partial match."""
    topic_lower = topic.lower().replace(" ", "_").replace("-", "_")

    # Exact match
    if topic_lower in RESEARCH_TOPICS:
        return RESEARCH_TOPICS[topic_lower]

    # Partial match
    for key, data in RESEARCH_TOPICS.items():
        if topic_lower in key or key in topic_lower:
            return data
        if topic_lower in data["title"].lower():
            return data

    # Fallback: generate a generic response
    return {
        "title": topic,
        "summary": f"Research on {topic}: This is an emerging field with growing investment and interest. Further details require specialized databases.",
        "facts": {"topic": topic, "status": "emerging"},
    }


def get_weather(city: str) -> Optional[Dict[str, Any]]:
    """Look up weather by city name."""
    city_key = city.lower().replace(" ", "_")
    if city_key in WEATHER_DATA:
        return WEATHER_DATA[city_key]
    # Partial match
    for key, data in WEATHER_DATA.items():
        if city.lower() in data["city"].lower() or data["city"].lower() in city.lower():
            return data
    return {"city": city, "temp_c": 20, "condition": "Unknown", "humidity": 50, "wind_kph": 10}


def get_flights(from_city: str, to_city: str) -> List[Dict[str, Any]]:
    """Look up flights between cities."""
    # Build route key
    city_codes = {
        "san francisco": "sfo",
        "sfo": "sfo",
        "new york": "jfk",
        "jfk": "jfk",
        "nyc": "jfk",
        "london": "lhr",
        "lhr": "lhr",
        "paris": "cdg",
        "cdg": "cdg",
        "tokyo": "nrt",
        "nrt": "nrt",
        "sydney": "syd",
        "syd": "syd",
    }
    from_code = city_codes.get(from_city.lower(), from_city.lower()[:3])
    to_code = city_codes.get(to_city.lower(), to_city.lower()[:3])

    route = f"{from_code}_{to_code}"
    if route in FLIGHT_DATA:
        return FLIGHT_DATA[route]

    # Reverse check
    route_rev = f"{to_code}_{from_code}"
    if route_rev in FLIGHT_DATA:
        return [dict(f, departure="return") for f in FLIGHT_DATA[route_rev]]

    return [{"airline": "Generic Air", "flight": "GA001", "price": 500, "stops": 1}]


def get_hotels(city: str) -> List[Dict[str, Any]]:
    """Look up hotels in a city."""
    city_key = city.lower().replace(" ", "_")
    if city_key in HOTEL_DATA:
        return HOTEL_DATA[city_key]
    for key, data in HOTEL_DATA.items():
        if city.lower() in key:
            return data
    return [{"name": f"Hotel {city}", "stars": 3, "price_night": 100, "rating": 3.5}]


def get_database_query(query: str) -> Any:
    """Simulate a database query."""
    query_lower = query.lower()
    for key, data in DATABASE_RESULTS.items():
        if key in query_lower:
            return data
    return {"result": "No matching records found", "query": query}


def get_api_result(endpoint: str) -> Any:
    """Simulate an API fetch."""
    endpoint_lower = endpoint.lower().replace(" ", "_")
    for key, data in API_RESULTS.items():
        if key in endpoint_lower or endpoint_lower in key:
            return data
    return {"endpoint": endpoint, "status": "ok", "data": "generic response"}


def get_calculation(expression: str) -> Any:
    """Compute a mathematical expression (safely)."""
    # Check pre-computed
    if expression in CALCULATION_RESULTS:
        return CALCULATION_RESULTS[expression]
    # Try safe eval
    try:
        # Only allow digits, operators, parens, spaces, dots
        import re

        if re.match(r"^[\d\s\+\-\*\/\.\(\)]+$", expression):
            return eval(expression)
    except Exception:
        pass
    return {"error": f"Cannot compute: {expression}"}
