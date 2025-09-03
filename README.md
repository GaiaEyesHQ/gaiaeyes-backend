# Gaia Eyes Backend (FastAPI)

## Quickstart
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then edit values
uvicorn app.main:app --reload
