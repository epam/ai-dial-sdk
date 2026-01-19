import os
import uvicorn

# The example creates Pydantic V2 models.
# In order to make them compatible with the models used in the DIAL SDK
# we need to enable the compatibility mode with Pydantic V2 via the env variable:
os.environ["PYDANTIC_V2"] = "True"

# Run built app
if __name__ == "__main__":
    from app.main import app
    uvicorn.run(app, port=5000)
