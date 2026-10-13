"""Interactive HTTP client for the Session 2 research catalogue."""
import requests

API_BASE_URL = "http://127.0.0.1:8000"
REQUEST_TIMEOUT_SECONDS = 30


def api_request(method, endpoint, **options):
    response = requests.request(
        method,
        f"{API_BASE_URL}{endpoint}",
        timeout=REQUEST_TIMEOUT_SECONDS,  # Bound the wait for the server.
        **options,
    )
    if not response.ok:
        print("API error:", response.status_code, response.text)
        return None
    return response.json()  # Decode the successful JSON response.


def main():
    print("Research catalogue client:", API_BASE_URL)
    while True:
        command = input("Choose list, read, write or quit: ").strip().lower()
        if command == "quit":
            break
        try:
            if command == "list":
                result = api_request("GET", "/papers", params={"limit": 50})
                if result is not None:
                    for paper in result["papers"]:
                        print(paper["paper_id"], "—", paper["title"])
            elif command == "read":
                paper_id = input("Paper ID: ").strip()
                result = api_request("GET", "/notes", params={"paper_id": paper_id})
                if result is not None:
                    print(result["note"])
            elif command == "write":
                paper_id = input("Paper ID: ").strip()
                note = input("Note text: ").strip()
                result = api_request(
                    "PUT", "/notes", json={"paper_id": paper_id, "note": note},
                )  # Send the note as a JSON request body.
                if result is not None:
                    print("Saved:", result)
            else:
                print("Enter list, read, write or quit.")
        except requests.RequestException as error:
            print("Request failed:", error)
        except ValueError as error:
            print("Could not decode the response:", error)


if __name__ == "__main__":
    main()
