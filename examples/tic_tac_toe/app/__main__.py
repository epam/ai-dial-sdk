import os

import uvicorn

os.environ["PYDANTIC_V2"] = "True"

if __name__ == "__main__":
    from .main import app

    uvicorn.run(app, port=5000)
