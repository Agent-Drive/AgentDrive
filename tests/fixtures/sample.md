---
title: API Reference
author: Engineering
---

# API Reference

## Authentication

OAuth2 is used for all API authentication. Tokens expire after 30 minutes. All requests must include a valid Bearer token in the Authorization header. Expired tokens will return a 401 Unauthorized response and must be refreshed using the refresh token endpoint before retrying the original request.

### OAuth2 Flow

The client obtains an authorization code and exchanges it for tokens. The authorization code is single-use and expires after 10 minutes. Store refresh tokens securely — they are long-lived and grant full API access.

```python
response = client.get_token(code=auth_code)
```

### API Keys

For server-to-server communication, use API keys instead. API keys do not expire but can be revoked at any time from the dashboard. Each key is scoped to a specific set of permissions and should follow the principle of least privilege.

## Users

### Create User

POST /v1/users creates a new user account. The request body must be JSON. On success the endpoint returns 201 Created with the new user object including the assigned ID. Email addresses must be unique across the system.

| Field | Type | Required |
|-------|------|----------|
| name | string | yes |
| email | string | yes |

### Delete User

DELETE /v1/users/:id removes the user and all associated data. This action is irreversible. A 204 No Content response is returned on success. Attempting to delete a non-existent user returns 404 Not Found.
