# eKYC Platform Setup Guide

## 1. Get Render PostgreSQL URL (Production Database)

If you are proceeding with Render's PostgreSQL (accepting the limitations of the free tier or upgrading to paid), here is how to get the connection URL:

1.  **Log in to Render**: Go to [dashboard.render.com](https://dashboard.render.com/).
2.  **Create New PostgreSQL**:
    *   Click **New +** button in the top right.
    *   Select **PostgreSQL**.
    *   **Name**: Give it a name (e.g., `ekyc-db`).
    *   **Region**: Choose the same region as your web service (e.g., `Singapore` or `Frankfurt`) for lowest latency.
    *   **Version**: Default (e.g., 16) is fine.
    *   **Instance Type**: Select **Free** (runs for 30 days only) or minimal paid tier (~$7/mo).
    *   Click **Create Database**.
3.  **Get the URL**:
    *   Wait a moment for the database to become "Available".
    *   Look for the **Connections** section on the database dashboard.
    *   Find **Internal Database URL** (for connecting from your Render Web Service).
        *   Format: `postgres://ekyc_user:password@dpg-xxxx-a:5432/ekyc_db`
    *   **Copy** this URL.

### Update Environment Variables
In your Render **Web Service** settings (not the database settings):
1.  Go to **Environment**.
2.  Add/Update the key `DATABASE_URL`.
3.  Paste the **Internal Database URL** you just copied.

---

## 2. AWS Configuration (Transcription)
*   **Get Keys**: AWS Console -> IAM -> Users -> Security Credentials.
*   **Env Vars**:
    *   `AWS_ACCESS_KEY_ID`: `AKIA...`
    *   `AWS_SECRET_ACCESS_KEY`: `secret...`
    *   `AWS_REGION`: `us-east-1`

## 3. LiveKit Configuration (Video)
*   **Get Keys**: LiveKit Cloud -> Settings -> Keys.
*   **Env Vars**:
    *   `LIVEKIT_URL`: `wss://...`
    *   `LIVEKIT_API_KEY`: `API...`
    *   `LIVEKIT_API_SECRET`: `secret...`

## 4. Security
*   **Env Var**:
    *   `SECRET_KEY`: `(Generate a random string)`
