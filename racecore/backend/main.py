from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="RaceCore API", description="Race Strategy Simulator and Mission Control")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "OK", "message": "RaceCore API is running"}

@app.get("/")
async def root():
    return {"message": "Welcome to RaceCore API"}