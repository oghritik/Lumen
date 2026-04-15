"""Wishlist-specific business logic helpers."""

CATEGORY_KEYWORDS = {
    "groceries": ["grocery", "vegetable", "fruit", "food", "supermarket", "mart", "store"],
    "dining": ["restaurant", "cafe", "coffee", "pizza", "burger", "meal", "dine"],
    "transportation": ["uber", "ola", "taxi", "metro", "bus", "train", "fuel", "petrol"],
    "utilities": ["electricity", "water", "gas", "internet", "mobile", "recharge", "bill"],
    "entertainment": ["movie", "cinema", "game", "music", "spotify", "netflix", "prime"],
    "shopping": ["clothes", "shoes", "dress", "shirt", "jeans", "fashion", "amazon", "flipkart"],
    "healthcare": ["medicine", "doctor", "hospital", "pharmacy", "health", "medical"],
    "education": ["book", "course", "class", "tuition", "study", "school", "college"],
    "electronics": ["phone", "laptop", "computer", "tablet", "camera", "headphone", "speaker"],
    "home": ["furniture", "decor", "appliance", "kitchen", "bedroom", "cleaning"],
}


def categorize_item(item_name: str) -> str:
    """Categorize a wishlist item using keyword matching."""
    item_lower = item_name.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in item_lower for keyword in keywords):
            return category
    return "other"


def serialize_wishlist_items(wishlist_items):
    """Serialize ORM wishlist rows into template-friendly dictionaries."""
    return [
        {
            "wishlist_id": item.wishlist_id,
            "item_name": item.item_name,
            "expected_price": item.expected_price,
            "category": item.category or "uncategorized",
            "notes": item.notes,
            "created_at": item.created_at.strftime("%B %d, %Y at %I:%M %p") if item.created_at else "",
        }
        for item in wishlist_items
    ]
