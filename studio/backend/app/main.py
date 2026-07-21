from fastapi import FastAPI

app = FastAPI(title="Virtual Model Studio backend")


@app.get("/health")
def health():
    return {"status": "ok"}
