from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

from config import settings
from database.database import init_db
from routes import auth, kyc, documents, face, video

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} started")
    yield
    # Shutdown
    print("👋 Shutting down...")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Electronic Know Your Customer Platform with document verification, face matching, liveness detection, and video verification.",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(kyc.router)
app.include_router(documents.router)
app.include_router(face.router)
app.include_router(video.router)

# Static files
static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

# Serve uploaded files (for admin viewing)
uploads_path = settings.UPLOAD_DIR
if os.path.exists(uploads_path):
    app.mount("/uploads", StaticFiles(directory=uploads_path), name="uploads")

# Serve recordings
recordings_path = os.path.join(os.path.dirname(__file__), "recordings")
if not os.path.exists(recordings_path):
    os.makedirs(recordings_path)
app.mount("/recordings", StaticFiles(directory=recordings_path), name="recordings")

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main application page"""
    index_path = os.path.join(static_path, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>eKYC Platform</title>
        <style>
            body { 
                font-family: system-ui; 
                display: flex; 
                justify-content: center; 
                align-items: center; 
                height: 100vh; 
                margin: 0;
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                color: white;
            }
            .container { text-align: center; }
            h1 { font-size: 3rem; margin-bottom: 1rem; }
            p { opacity: 0.8; }
            a { color: #00d9ff; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔐 eKYC Platform</h1>
            <p>Electronic Know Your Customer Verification System</p>
            <p>API Documentation: <a href="/docs">/docs</a></p>
        </div>
    </body>
    </html>
    """)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8002)
