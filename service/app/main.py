from fastapi import FastAPI

app = FastAPI(title="Dialogic Voice Partner Service", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used by the desktop shell before enabling the UI."""
    return {"status": "ok"}
