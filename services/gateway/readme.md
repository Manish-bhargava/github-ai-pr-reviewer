


# Gateway Service API

## Health

GET /health

Returns service health status.

---

## GitHub Webhook

POST /webhook/github

Receives GitHub webhooks and forwards them to the Webhook Service.

---

## GitHub Login

GET /auth/github/login

Returns GitHub OAuth login URL.

---

## GitHub OAuth Callback

GET /auth/github/callback

Exchanges GitHub OAuth code for access token.

Query Parameters:

* code

---

## Current User

GET /me

Returns authenticated GitHub user information.

Query Parameters:

* token

---

## List Repositories

GET /repos

Returns repositories accessible by the authenticated user.

Query Parameters:

* token

---

## List Pull Requests

GET /repos/{owner}/{repo}/pulls

Returns open pull requests for a repository.

Path Parameters:

* owner
* repo

Query Parameters:

* token

---

## Trigger AI Review

POST /review

Triggers AI review of a pull request.

Request Body:

{
"owner": "string",
"repo": "string",
"pr_number": 0
}

Response:

{
"status": "success"
}
