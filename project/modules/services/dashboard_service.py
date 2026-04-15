"""Business logic for dashboard data payload generation."""

from datetime import datetime, timedelta


def build_dashboard_payload(transactions):
    """Build a charts-friendly dashboard payload from transactions."""
    debit_total = sum(t.amount or 0 for t in transactions if t.type == "debit")
    credit_total = sum(t.amount or 0 for t in transactions if t.type == "credit")
    net_flow = credit_total - debit_total

    categories = {}
    for txn in transactions:
        if txn.category and txn.type == "debit":
            categories[txn.category] = categories.get(txn.category, 0) + (txn.amount or 0)

    sorted_categories = sorted(categories.items(), key=lambda item: item[1], reverse=True)[:5]
    donut_labels = [cat for cat, _ in sorted_categories] or ["No Data"]
    donut_values = [val for _, val in sorted_categories] or [0]

    today = datetime.now()
    daily_spending = {}
    for i in range(7):
        date_key = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        daily_spending[date_key] = 0

    for txn in transactions:
        if txn.date and txn.type == "debit" and txn.date in daily_spending:
            daily_spending[txn.date] += txn.amount or 0

    line_labels = list(daily_spending.keys())
    line_values = list(daily_spending.values())

    return {
        "success": True,
        "debit_total": debit_total,
        "credit_total": credit_total,
        "net_flow": net_flow,
        "donut_labels": donut_labels,
        "donut_values": donut_values,
        "mini_labels": donut_labels[:3],
        "mini_values": donut_values[:3],
        "line_labels": line_labels,
        "line_values": line_values,
    }


def build_dashboard_error_payload(error_message: str):
    """Build a stable fallback payload when dashboard computation fails."""
    return {
        "success": False,
        "error": error_message,
        "debit_total": 0,
        "credit_total": 0,
        "net_flow": 0,
        "donut_labels": ["No Data"],
        "donut_values": [0],
        "mini_labels": ["No Data"],
        "mini_values": [0],
        "line_labels": ["No Data"],
        "line_values": [0],
    }
