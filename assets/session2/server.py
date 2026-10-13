"""Run from the course repository after collecting the Lab 1 CSV."""
import pandas as pd
import os

DATA_DIRECTORY = "sample_data/session2"
PAPERS_CSV = f"{DATA_DIRECTORY}/papers.csv"
os.makedirs(DATA_DIRECTORY, exist_ok=True)

import json
import threading
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

app = FastAPI(title="Research Catalogue API")  # Used in generated API documentation.
NOTES_JSON = f"{DATA_DIRECTORY}/notes.json"
storage_lock = threading.Lock()  # Serialise file access within this server process.

class NoteInput(BaseModel):
    paper_id: str = Field(min_length=1, max_length=100)  # Required catalogue identifier.
    note: str = Field(min_length=1, max_length=2000)  # Bound the note size.

@app.get("/health")  # Register a GET route.
def health():
    return {"status": "ok", "service": "research-catalogue"}

def read_papers():
    try:
        catalogue = pd.read_csv(
            PAPERS_CSV,
            dtype=str,  # Keep identifiers and dates as text.
            keep_default_na=False,  # Keep empty fields as strings rather than NaN.
            encoding="utf-8",  # Read Unicode titles and author names.
        )
        return catalogue.to_dict(orient="records")  # Convert rows to JSON-ready dictionaries.
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Run Lab 1 to create papers.csv.")

@app.get("/papers")
def list_papers(limit: int = Query(default=5, ge=1, le=50)):
    # Accept a query parameter between 1 and 50.
    catalogue = read_papers()
    return {"total": len(catalogue), "papers": catalogue[:limit]}

def read_notes():
    try:
        with open(NOTES_JSON, "r", encoding="utf-8") as notes_file:
            return json.load(notes_file)  # Convert JSON text to a dictionary.
    except FileNotFoundError:
        return {}

@app.get("/notes")
def get_note(paper_id: str = Query(min_length=1, max_length=100)):
    with storage_lock:
        notes = read_notes()
    if paper_id not in notes:
        raise HTTPException(status_code=404, detail="No note saved for this paper.")
    return {"paper_id": paper_id, "note": notes[paper_id]}

@app.put("/notes")
def save_note(payload: NoteInput):
    if not payload.note.strip():
        raise HTTPException(status_code=422, detail="The note must contain text.")
    with storage_lock:
        if payload.paper_id not in {paper["paper_id"] for paper in read_papers()}:
            raise HTTPException(status_code=404, detail="Paper not found in the catalogue.")
        notes = read_notes()
        notes[payload.paper_id] = payload.note
        temporary_file = f"{NOTES_JSON}.tmp"
        with open(temporary_file, "w", encoding="utf-8") as notes_file:
            json.dump(notes, notes_file, ensure_ascii=False, indent=2)  # Preserve Unicode.
        os.replace(temporary_file, NOTES_JSON)  # Replace the file after writing completes.
    return payload.model_dump()  # Return the validated stored representation.

if __name__ == "__main__":
    import uvicorn

    # Bind to the local computer and use one worker for file storage.
    uvicorn.run(app, host="127.0.0.1", port=8000)
