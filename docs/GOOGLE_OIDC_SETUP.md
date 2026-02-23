# Google OIDC Authentication Setup

This guide explains how to set up Google OIDC authentication for the Interview Helper application.

## Prerequisites

You need to create a Google OAuth2 application in the Google Cloud Console.

## Setup Steps

### 1. Create Google OAuth2 Credentials

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Navigate to "APIs & Services" > "Credentials"
4. Click "Create Credentials" > "OAuth 2.0 Client IDs"
5. Configure the consent screen if prompted
6. Choose "Web application" as the application type
7. Add authorized redirect URIs:
   - `http://localhost:3000/auth/callback` (backend)
   - `http://localhost:5173/auth/callback` (frontend - for development)
8. Save and note your Client ID and Client Secret

### 2. Configure Environment Variables

#### Backend (.env)
```env
# Server Configuration
SERVER_HOST=0.0.0.0
SERVER_PORT=3000

# CORS Configuration
CORS_ALLOW_ORIGINS=http://localhost:5173,http://localhost:3000

# Google OIDC Configuration
GOOGLE_CLIENT_ID=your-actual-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-actual-google-client-secret
SITE_URL=http://localhost:3000
FRONTEND_REDIRECT_URI=http://localhost:5173/auth/callback
```

#### Frontend (.env)
```env
VITE_BACKEND_URL=http://localhost:3000
VITE_SITE_URL=http://localhost:5173
VITE_OIDC_AUTHORITY=https://accounts.google.com
VITE_OIDC_CLIENT_ID=your-actual-google-client-id.apps.googleusercontent.com
```

### 3. Start the Applications

#### Backend
```bash
cd backend
python -m pip install -e .
python src/main.py
```

#### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Authentication Flow

1. User visits the frontend application
2. If not authenticated, user sees the Google login button
3. User clicks "Sign in with Google"
4. User is redirected to Google for authentication
5. After successful authentication, user is redirected back to the application
6. The application shows the authenticated user interface

## Security Features

- JWT token verification using Google's public keys
- Secure token exchange (authorization code flow)
- CORS protection
- Proper error handling for authentication failures

## Testing

The application includes a test script to validate the authentication configuration:

```bash
cd backend
python test_authentication.py
```

This will verify that all configuration is correct and the authentication flow is properly implemented.