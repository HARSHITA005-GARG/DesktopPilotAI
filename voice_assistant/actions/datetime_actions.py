from datetime import datetime


def get_datetime(kind=None):
    """Return the current local date, time, day, or all three."""
    now = datetime.now()
    requested = (kind or "datetime").strip().lower()

    if requested == "time":
        value = now.strftime("%I:%M %p").lstrip("0")
        message = f"The time is {value}."
    elif requested == "date":
        value = now.strftime("%B %d, %Y")
        message = f"Today's date is {value}."
    elif requested == "day":
        value = now.strftime("%A")
        message = f"Today is {value}."
    else:
        value = {
            "date": now.strftime("%B %d, %Y"),
            "day": now.strftime("%A"),
            "time": now.strftime("%I:%M %p").lstrip("0"),
        }
        message = f"Today is {value['day']}, {value['date']}. The time is {value['time']}."

    return {
        "status": "success",
        "message": message,
        "kind": requested,
        "value": value,
    }
