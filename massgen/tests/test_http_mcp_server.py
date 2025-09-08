"""Simple FastMCP Streamable HTTP Server"""
from mcp.server.fastmcp import FastMCP
from datetime import datetime
import random

mcp = FastMCP("simple_test")

@mcp.tool()
def get_events(day: str) -> str:
    """Get events for a day"""
    events = {
        "wednesday": "Team meeting at 10 AM",
        "friday": "Previews at 10 AM, Deploy at 4 PM"
    }
    return events.get(day.lower(), f"No events for {day}")

@mcp.tool()
def get_birthdays() -> str:
    """Get this week's birthdays"""
    return "Mom's birthday tomorrow, Sis's birthday Friday"

@mcp.tool()
def random_data(count: int = 3) -> str:
    """Generate random test data"""
    data = [f"Item {i+1}: {random.randint(1,100)}" for i in range(count)]
    return "\n".join(data)

@mcp.tool()
def server_status() -> str:
    """Server health check"""
    return f"✅ Healthy - {datetime.now().strftime('%H:%M:%S')}"

if __name__ == "__main__":
    print("🚀 Starting server at http://localhost:8000/mcp")
    mcp.run(transport="streamable-http")