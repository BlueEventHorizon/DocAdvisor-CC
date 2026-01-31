# Authentication API Design

## Overview

This document describes the API design for user authentication.

## Endpoints

### POST /api/auth/login

Request:
```json
{
  "email": "user@example.com",
  "password": "password123",
  "remember_me": true
}
```

Response:
```json
{
  "token": "jwt-token-here",
  "user": {
    "id": "123",
    "email": "user@example.com",
    "name": "John Doe"
  }
}
```

### POST /api/auth/register

Request:
```json
{
  "email": "user@example.com",
  "password": "password123",
  "name": "John Doe"
}
```

### POST /api/auth/reset-password

Request:
```json
{
  "email": "user@example.com"
}
```

## Error Codes

| Code | Description |
|------|-------------|
| 401 | Invalid credentials |
| 403 | Account locked |
| 422 | Validation error |

## Security Considerations

- JWT tokens expire after 1 hour
- Refresh tokens expire after 7 days
- All endpoints require HTTPS
