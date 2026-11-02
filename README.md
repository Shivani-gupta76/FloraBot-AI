# FloraBot-AI 🌱

**AI-Powered Crop Health Monitoring and Disease Detection System**

FloraBot-AI is a smart agriculture project designed to support crop health monitoring through artificial intelligence. It combines a plant disease classification model with a web-based dashboard and backend services to help users manage crops, review disease detection results, monitor alerts, and maintain crop health records.

## 🚀 Features

- **AI-Based Disease Classification:** Uses YOLO11n-cls to classify plant leaf images into supported disease and healthy-plant categories.
- **Crop Management:** Provides a dashboard for managing crop records.
- **Disease Detection:** Supports image-based disease analysis and confidence reporting.
- **Interactive Dashboard:** React-based interface for viewing crop information, detection history, alerts, and reports.
- **Backend API:** FastAPI provides endpoints for application functionality.
- **Database Integration:** PostgreSQL is used for persistent application data.
- **Alerts and History:** Supports viewing relevant alerts and recorded application activity.
- **Demo Mode:** Allows users to explore dashboard functionality with example data.

## 🛠️ Technology Stack

| Component | Technology |
|---|---|
| AI/ML | Python, Ultralytics YOLO11n-cls, PyTorch |
| Frontend | React, Vite, JavaScript |
| Backend | FastAPI, Python |
| Database | PostgreSQL |
| Database Migrations | Alembic |
| Testing | Pytest, frontend tests |
| Version Control | Git, GitHub |

## 🏗️ Project Structure

```text
FloraBot-AI/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── services/
│   │   ├── main.py
│   │   └── schemas.py
│   ├── alembic/
│   ├── tests/
│   ├── requirements.txt
│   ├── requirements-inference.txt
│   └── .env.example
├── frontend/
│   ├── public/
│   ├── src/
│   ├── package.json
│   └── .env.example
└── README.md
```

## ⚙️ Getting Started

### Prerequisites

Install the following before running the project:

- Python 3.10 or a compatible version supported by the backend dependencies
- Node.js and npm
- PostgreSQL
- Git

### 1. Clone the Repository

```bash
git clone https://github.com/Shivani-gupta76/FloraBot-AI.git
cd FloraBot-AI
```

### 2. Set Up the Backend

Open a terminal in the project directory.

```bash
cd backend
python -m venv .venv
```

Activate the virtual environment on Windows:

```bat
.venv\Scripts\activate
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a local `.env` file using `backend/.env.example` as a reference. Configure the required database connection, authentication settings, and other variables according to the backend configuration.

Do not commit real passwords, API keys, or secret values to GitHub.

### 4. Set Up the Database

Create a PostgreSQL database and configure its connection string in the backend environment.

Apply database migrations using the project's Alembic configuration and migration scripts. Refer to `backend/README.md` for project-specific setup instructions.

### 5. Start the Backend

From the `backend` directory, run:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The backend API will be available at:

- API: http://127.0.0.1:8000
- Interactive API documentation: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/api/health

### 6. Start the Frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the local URL displayed by Vite, usually:

http://localhost:5173/

Configure the frontend environment variables using `frontend/.env.example` if required.

## 🧠 AI Model

FloraBot-AI uses the YOLO11n-cls image classification architecture for plant disease classification.

The model was trained using a combined dataset derived from PlantVillage and PlantDoc, covering 15 supported classes across tomato, potato, and pepper plants.

Reported evaluation results on the held-out test dataset:

- **Top-1 accuracy:** 96.6%
- **Top-5 accuracy:** 99.3%

These metrics describe performance on the test dataset and do not guarantee the same accuracy under real-world field conditions.

To enable local model inference, install the appropriate dependencies listed in `backend/requirements-inference.txt` and configure the trained model weights at the location expected by the inference service.

The trained model weights are not included in this repository by default. Actual inference requires the weights and runtime dependencies to be available.

## 🧪 Testing

Run backend tests from the `backend` directory:

```bash
pytest
```

Run frontend tests from the `frontend` directory using the test script defined in `package.json`.

Build the frontend for production with:

```bash
npm run build
```

## 🔮 Future Improvements

- Integrate the camera with the disease classification pipeline.
- Complete and validate end-to-end image inference and detection history.
- Integrate Raspberry Pi-based image capture and processing.
- Integrate ESP32-based hardware control where applicable.
- Validate the application using real crop images collected under field conditions.
- Improve deployment, monitoring, and production configuration.




