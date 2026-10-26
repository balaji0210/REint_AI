"""FastAPI application entry point for the wind forecast dashboard backend."""
from fastapi import FastAPI

app = FastAPI(title="UK Wind Power Forecasting & Accuracy API")


@app.get("/health")
def health_check():
    return {"status": "ok"}
