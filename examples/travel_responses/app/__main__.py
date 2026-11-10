import uvicorn

if __name__ == "__main__":
    from .main import app

    uvicorn.run(app, port=5000)
