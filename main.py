from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from routes import router
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB connection
MONGODB_URL = os.getenv("MONGODB_URL")


@app.on_event("startup")
async def startup_db_client():
    app.state.db_client = AsyncIOMotorClient(MONGODB_URL)
    app.state.db = app.state.db_client["backpack"]


@app.on_event("shutdown")
async def shutdown_db_client():
    app.state.db_client.close()


# Include routes
app.include_router(router)


@app.get("/")
async def root():
    return {"message": "Backpack API is running"}
