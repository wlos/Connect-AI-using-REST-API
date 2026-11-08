# Teaching companion to Session 2: Creating APIs with FastAPI.

from fastapi import FastAPI

# Give the application a title for its interactive documentation.
app = FastAPI(title="Demonstration Weather API")


@app.get("/")
def root():
    """Return a welcome message."""
    return {"message": "Hello, World!"}


@app.get("/weather")
def demo_weather(city: str):
    """Return fixed sample weather for a requested city."""
    return {"city": city, "temp_c": 25.0, "condition": "Sunny"}
