# Neighborhood Civic Help — Flask project

A runnable Flask + SQLite web app based on the uploaded Neighborhood Civic Help interface.

## Features
- User login with full name and 10-digit mobile number (no password; this is suitable for a college/demo project, not identity verification).
- Submit a problem with area, description, optional photo, and browser GPS coordinates (only after the user allows location access).
- Submit feedback / thank-you notes / not-solved reports.
- Admin PIN login (default `2422`) to view reports and feedback, download a combined CSV, download photos, open coordinates in Google Maps, and delete records.
- Records persist in `civic_help.db`; uploads are stored under `uploads/`.

## Run on Windows (VS Code / PowerShell)
1. Extract this ZIP to a folder.
2. Open the folder in VS Code.
3. In the terminal run:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   py app.py
   ```
   If PowerShell blocks activation, use Command Prompt:
   ```bat
   .venv\Scripts\activate.bat
   ```
   Or skip activation and run:
   ```powershell
   py -m pip install -r requirements.txt
   py app.py
   ```
4. Open `http://127.0.0.1:5000` in your browser.
5. Click **Admin** and enter PIN `2422`.

## Location notes
Browser geolocation generally requires `localhost`/`127.0.0.1` or HTTPS and asks the user for permission. It cannot silently fetch GPS coordinates without permission. Reports can still be submitted if location access is denied.

## Security / deployment notes
- The default admin PIN is `2422` as requested. For any deployment beyond a local demo, set a strong secret and PIN in environment variables:
  - `FLASK_SECRET_KEY`
  - `CIVIC_ADMIN_PIN`
- This simple demo uses name + mobile number as login, not OTP or password authentication. Do not expose it publicly with real residents' personal information until proper authentication, HTTPS, access controls, backups, and privacy notices are added.
- Uploaded photos are limited to 8 MB and served only to an authenticated admin.
- The development server is for local testing only.
