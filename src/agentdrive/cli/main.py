import os
import time
import webbrowser

import httpx
import typer

from agentdrive.cli.credentials import delete_credentials, load_credentials, save_credentials

app = typer.Typer(name="agentdrive", help="Agent Drive CLI")

DEFAULT_API_URL = "http://localhost:8080"
WORKOS_AUTHKIT_DOMAIN = os.environ.get("WORKOS_AUTHKIT_DOMAIN", "")
WORKOS_CLIENT_ID = os.environ.get("WORKOS_CLIENT_ID", "")


def _get_api_url() -> str:
    return os.environ.get("AGENT_DRIVE_URL", DEFAULT_API_URL)


@app.command()
def login():
    """Authenticate with Agent Drive via browser login (WorkOS device flow)."""
    if not WORKOS_AUTHKIT_DOMAIN or not WORKOS_CLIENT_ID:
        typer.echo("Error: WORKOS_AUTHKIT_DOMAIN and WORKOS_CLIENT_ID must be set.", err=True)
        raise typer.Exit(1)

    authkit_base = f"https://{WORKOS_AUTHKIT_DOMAIN}"

    typer.echo("Starting login...")
    with httpx.Client(timeout=30) as client:
        resp = client.post(
            f"{authkit_base}/authorize/device",
            data={"client_id": WORKOS_CLIENT_ID},
        )
        if resp.status_code != 200:
            typer.echo(f"Error starting device auth: {resp.text}", err=True)
            raise typer.Exit(1)
        data = resp.json()

    device_code = data["device_code"]
    user_code = data["user_code"]
    verification_uri = data.get("verification_uri_complete", data["verification_uri"])
    interval = data.get("interval", 5)

    typer.echo(f"\n  Your code: {user_code}")
    typer.echo(f"  Press Enter to open browser, or visit: {verification_uri}")
    input()
    webbrowser.open(verification_uri)

    typer.echo("Waiting for authentication...")
    with httpx.Client(timeout=30) as client:
        for _ in range(60):
            time.sleep(interval)
            resp = client.post(
                f"{authkit_base}/token",
                data={
                    "client_id": WORKOS_CLIENT_ID,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
            )
            if resp.status_code == 200:
                token_data = resp.json()
                access_token = token_data["access_token"]

                api_url = _get_api_url()
                exchange_resp = httpx.post(
                    f"{api_url}/auth/exchange",
                    json={"access_token": access_token},
                    timeout=30,
                )
                if exchange_resp.status_code != 200:
                    typer.echo(f"Error exchanging token: {exchange_resp.text}", err=True)
                    raise typer.Exit(1)

                result = exchange_resp.json()
                save_credentials(
                    api_key=result["api_key"],
                    email=result["email"],
                    tenant_id=result["tenant_id"],
                )
                typer.echo(f"\n  Logged in as {result['email']}")
                typer.echo("  API key stored in ~/.agentdrive/credentials")
                typer.echo("  Ready to use!")
                return

            error = resp.json().get("error", "")
            if error == "slow_down":
                interval += 5
            elif error in ("access_denied", "expired_token"):
                typer.echo(f"Login failed: {error}", err=True)
                raise typer.Exit(1)

    typer.echo("Login timed out. Please try again.", err=True)
    raise typer.Exit(1)


@app.command()
def logout():
    """Remove stored credentials."""
    delete_credentials()
    typer.echo("Logged out. Credentials removed.")


@app.command()
def status():
    """Show current authentication status."""
    creds = load_credentials()
    if not creds:
        typer.echo("Not logged in. Run 'agentdrive login' to authenticate.")
        raise typer.Exit(1)
    typer.echo(f"  Email:     {creds['email']}")
    typer.echo(f"  Tenant:    {creds['tenant_id']}")
    typer.echo(f"  Key:       {creds['api_key'][:14]}...")
    typer.echo(f"  Since:     {creds.get('created_at', 'unknown')}")


@app.command()
def keys():
    """List API keys for your tenant."""
    creds = load_credentials()
    if not creds:
        typer.echo("Not logged in. Run 'agentdrive login' first.", err=True)
        raise typer.Exit(1)

    api_url = _get_api_url()
    with httpx.Client(base_url=api_url, timeout=30) as client:
        resp = client.get(
            "/v1/api-keys",
            headers={"Authorization": f"Bearer {creds['api_key']}"},
        )
        if resp.status_code != 200:
            typer.echo(f"Error: {resp.text}", err=True)
            raise typer.Exit(1)

    data = resp.json()
    if data["total"] == 0:
        typer.echo("No API keys found.")
        return

    typer.echo(f"\n  {'PREFIX':<12} {'NAME':<20} {'CREATED':<22} {'LAST USED':<22} {'STATUS'}")
    typer.echo(f"  {'─' * 12} {'─' * 20} {'─' * 22} {'─' * 22} {'─' * 10}")
    for key in data["api_keys"]:
        name = key.get("name") or "(none)"
        created = key["created_at"][:19] if key["created_at"] else "—"
        last_used = key["last_used"][:19] if key.get("last_used") else "never"
        status = "revoked" if key.get("revoked_at") else "active"
        typer.echo(f"  {key['key_prefix']:<12} {name:<20} {created:<22} {last_used:<22} {status}")


if __name__ == "__main__":
    app()
