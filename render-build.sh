#!/usr/bin/env bash
# exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt
pip install asyncpg psycopg2-binary

# Create directories if they don't exist
mkdir -p uploads/documents
mkdir -p uploads/faces
mkdir -p recordings
mkdir -p transcription

# Run application
uvicorn main:app --host 0.0.0.0 --port 10000
