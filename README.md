# Backpack - Backend

This is the backend API for Backpack, a job costing application built with FastAPI and MongoDB.

## Live API

https://backpackapp.duckdns.org/docs

## How to Run Locally

You need Python 3.10 or higher installed.

1. Clone the repository

    git clone https://github.com/manikantakallakuri8-bit/backpack-be.git
    cd backpack-be

2. Create and activate a virtual environment

   On Windows:

    python -m venv venv
    venv\Scripts\activate

   On Mac or Linux:

    python3 -m venv venv
    source venv/bin/activate

3. Install dependencies

    pip install -r requirements.txt

4. Create a file named .env in the project folder with these values:

    MONGODB_URL=your_mongodb_connection_string_here
    SECRET_KEY=your_secret_key_here
    ALGORITHM=HS256
    ACCESS_TOKEN_EXPIRE_MINUTES=480
    GROQ_API_KEY=your_groq_api_key_here
    GROQ_BASE_URL=https://api.groq.com/openai/v1
    GROQ_MODEL=llama-3.1-8b-instant

5. Start the server

    uvicorn main:app --reload

The API runs at http://localhost:8000

Open http://localhost:8000/docs to see and test all the endpoints.
