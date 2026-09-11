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
venv\Scripts\activate  # On Windows
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