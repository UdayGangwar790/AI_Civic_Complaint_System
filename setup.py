import os
import json

base_dir = r"c:\Users\sushm\OneDrive\Desktop\CIVKI"

folders = [
    "frontend",
    "backend/app/api",
    "backend/app/models",
    "backend/app/schemas",
    "backend/app/services",
    "backend/app/core",
    "backend/app/utils",
    "ai/computer_vision/dataset_source/01_Open_Damaged_Manhole",
    "ai/computer_vision/dataset_source/02_Damaged_Missing_Road_Signs",
    "ai/computer_vision/dataset_source/03_Road_Waterlogging",
    "ai/computer_vision/dataset/images/train",
    "ai/computer_vision/dataset/images/val",
    "ai/computer_vision/dataset/images/test",
    "ai/computer_vision/dataset/labels/train",
    "ai/computer_vision/dataset/labels/val",
    "ai/computer_vision/dataset/labels/test",
    "ai/computer_vision/models",
    "ai/computer_vision/scripts",
    "ai/computer_vision/training",
    "ai/computer_vision/inference",
    "ai/nlp/models",
    "ai/nlp/training",
    "ai/nlp/inference",
    "data/raw",
    "data/processed",
    "data/annotations",
    "docs"
]

for folder in folders:
    os.makedirs(os.path.join(base_dir, folder), exist_ok=True)

files = {
    ".gitignore": """
node_modules/
__pycache__/
*.pyc
.env
venv/
env/
.DS_Store
dist/
build/
# IMPORTANT: Ignore the source dataset files to prevent committing large private images
ai/computer_vision/dataset_source/
ai/computer_vision/dataset/
data/raw/
data/processed/
""",
    ".env.example": """
# MongoDB Configuration
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB_NAME=cvki

# Security
JWT_SECRET=your_super_secret_jwt_key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# External APIs
OPENROUTER_API_KEY=your_openrouter_api_key
""",
    "README.md": """
# CVKI (Civic Vision & Knowledge Intelligence)

## 1. What is CVKI?
CVKI is an end-to-end civic-tech platform designed to empower citizens to capture road and civic problems, automatically identify them using AI, determine their location, map them to the responsible authority, and guide the complaint generation and tracking process.

## 2. Real-world Problem Being Solved
Citizens often face civic issues like damaged roads, missing signs, or waterlogging but struggle to identify the exact problem, the responsible department, or the formal way to file a complaint. CVKI bridges this gap using Computer Vision, NLP, and Geospatial mapping.

## 3. Three Initial Detection Classes
The initial implementation of the Computer Vision module will focus on three critical civic problems:
1. `open_damaged_manhole` (Class 0)
2. `damaged_missing_road_sign` (Class 1)
3. `road_waterlogging` (Class 2)

## 4. Overall Architecture
- **Frontend**: React, Vite, Tailwind CSS (Citizen Dashboard, Complaint Tracking)
- **Backend**: FastAPI, Python (Modular architecture for APIs, user auth, and DB operations)
- **Database**: MongoDB (Storing users, complaints, locations, etc.)
- **AI Modules**: YOLO-family object detection (CV), Hugging Face Transformers (NLP)

## 5. Current Development Stage
The project is currently in the **foundation** phase. The monorepo structure has been created, frontend and backend placeholders are set up, and the architecture is ready for incremental AI module integration. No AI training or detection is currently active.

## 6. Project Folder Structure
```
CVKI/
├── frontend/             # React application
├── backend/              # FastAPI application
├── ai/
│   ├── computer_vision/  # YOLO-based vision models
│   └── nlp/              # NLP intelligence (future)
├── data/                 # Raw and processed datasets
└── docs/                 # Documentation
```

## 7. Dataset Folder Structure
Initial real-world dataset will be placed in:
```
ai/computer_vision/dataset_source/
├── 01_Open_Damaged_Manhole/
├── 02_Damaged_Missing_Road_Signs/
└── 03_Road_Waterlogging/
```
*Note: This will consist of approximately 100 user-provided Indian road images per class (Total ~300 images).*

## 8. Future YOLO Workflow
Source Images -> Validate -> Annotate -> Convert to YOLO labels -> Train/Val/Test Split -> Train YOLO -> Evaluate -> Save best.pt -> Inference API.

## 9. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

## 10. Backend Setup
```bash
cd backend
python -m venv venv
venv\\Scripts\\activate  # On Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## 11. Environment Variables
Copy `.env.example` to `.env` and fill in the required values. **Never hardcode secrets in the source code.**

## 12. How to Run the Project
1. Start the backend server (runs on port 8000 by default).
2. Start the frontend development server (runs on port 5173 by default).
3. Access the frontend via browser and the backend API docs at `http://localhost:8000/docs`.

## 13. Future Development Roadmap
- Integrate YOLO object detection for the 3 core classes.
- Implement Location and Road Identification services.
- Implement NLP for intelligent complaint generation.
- Develop the Citizen Dashboard and escalation mechanisms.
""",
    "ai/computer_vision/data.yaml": """
# Future YOLO configuration file
path: ../dataset
train: images/train
val: images/val
test: images/test

# Classes
nc: 3
names:
  0: open_damaged_manhole
  1: damaged_missing_road_sign
  2: road_waterlogging
""",
    "ai/computer_vision/README.md": """
# Computer Vision Module

This module handles the object detection for civic problems using YOLO-family models.

## Dataset
Original images should be placed in `dataset_source/`.
Do NOT manually place images in the `dataset/` folder, as that will be generated via a pipeline.
""",
    "ai/nlp/README.md": """
# NLP Module

This module will handle complaint intelligence, severity assessment, and automated guidance using language models.
""",
    "backend/requirements.txt": """
fastapi==0.111.0
uvicorn==0.30.1
pydantic==2.7.4
pydantic-settings==2.3.4
motor==3.4.0
python-dotenv==1.0.1
""",
    "backend/app/__init__.py": "",
    "backend/app/api/__init__.py": "",
    "backend/app/models/__init__.py": "",
    "backend/app/schemas/__init__.py": "",
    "backend/app/services/__init__.py": "",
    "backend/app/core/__init__.py": "",
    "backend/app/utils/__init__.py": "",
    "backend/app/main.py": """
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.health import router as health_router

app = FastAPI(
    title="CVKI API",
    description="Backend API for Civic Vision & Knowledge Intelligence platform",
    version="0.1.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health_router, prefix="/api", tags=["health"])

@app.get("/")
def read_root():
    return {"message": "Welcome to CVKI Backend API. Visit /docs for documentation."}
""",
    "backend/app/api/health.py": """
from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "CVKI backend"
    }
""",
    "backend/app/services/computer_vision.py": """
# Placeholder for Computer Vision Service interface

def detect_problems(image_path: str):
    \"\"\"
    Analyze the image and detect civic problems.
    \"\"\"
    raise NotImplementedError("CV detection logic not implemented yet.")
""",
    "backend/app/services/location.py": """
# Placeholder for Location Service interface

def get_location_details(lat: float, lon: float):
    \"\"\"
    Reverse geocode coordinates.
    \"\"\"
    raise NotImplementedError("Location logic not implemented yet.")
""",
    "backend/app/services/authority.py": """
# Placeholder for Authority Identification Service

def identify_authority(location_data, problem_type):
    \"\"\"
    Map a problem and location to the responsible authority.
    \"\"\"
    raise NotImplementedError("Authority identification logic not implemented yet.")
""",
    "backend/app/services/nlp.py": """
# Placeholder for NLP Complaint Intelligence Service

def generate_complaint_text(problem_data, location_data):
    \"\"\"
    Generate a formal complaint text using AI.
    \"\"\"
    raise NotImplementedError("NLP logic not implemented yet.")
""",
}

for filepath, content in files.items():
    full_path = os.path.join(base_dir, filepath)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content.strip())

print("Project foundation created successfully!")
