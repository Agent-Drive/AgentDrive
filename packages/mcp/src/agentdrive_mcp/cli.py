import json
import os
import shutil
import subprocess
import time
import webbrowser
from pathlib import Path

import httpx
import typer

from agentdrive_mcp.credentials import delete_credentials, load_credentials, save_credentials

app = typer.Typer(name="agentdrive-mcp", help="Agent Drive MCP for Claude Code")

DEFAULT_API_URL = "https://api.agentdrive.so"
WORKOS_API_BASE = "https://api.workos.com"


def _get_api_url() -> str:
    return os.environ.get("AGENT_DRIVE_URL", DEFAULT_API_URL)


def _do_login(api_url: str) -> dict:
    """Run WorkOS device flow login. Returns {"api_key", "email", "tenant_id"}."""
    with httpx.Client(timeout=30) as client:
        config_resp = client.get(f"{api_url}/auth/config")
        if config_resp.status_code != 200:
            typer.echo(f"Error: could not reach Agent Drive at {api_url}", err=True)
            raise typer.Exit(1)
        client_id = config_resp.json()["client_id"]

        resp = client.post(
            f"{WORKOS_API_BASE}/user_management/authorize/device",
            json={"client_id": client_id},
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
    typer.echo(f"  Opening browser to: {verification_uri}")
    webbrowser.open(verification_uri)

    typer.echo("Waiting for authentication...")
    with httpx.Client(timeout=30) as client:
        for _ in range(60):
            time.sleep(interval)
            resp = client.post(
                f"{WORKOS_API_BASE}/user_management/authenticate",
                json={
                    "client_id": client_id,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
            )
            if resp.status_code == 200:
                token_data = resp.json()
                access_token = token_data["access_token"]

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
                return result

            error = resp.json().get("error", "")
            if error == "slow_down":
                interval += 5
            elif error in ("access_denied", "expired_token"):
                typer.echo(f"Login failed: {error}", err=True)
                raise typer.Exit(1)

    typer.echo("Login timed out. Please try again.", err=True)
    raise typer.Exit(1)


def _write_mcp_config(method: str, api_url: str) -> None:
    """Write MCP config to ~/.claude.json using claude CLI or direct JSON merge."""
    if method == "uvx":
        command = "uvx"
        args = ["agentdrive-mcp", "serve"]
    else:
        command = "agentdrive-mcp"
        args = ["serve"]

    # Try claude mcp add first (safest)
    if shutil.which("claude"):
        try:
            cmd = [
                "claude", "mcp", "add", "agent-drive",
                "--scope", "user",
                "-e", f"AGENT_DRIVE_URL={api_url}",
                "--", command, *args,
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass  # fall through to manual JSON

    # Fallback: direct JSON merge
    config_path = Path.home() / ".claude.json"
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text())

    if "mcpServers" not in config:
        config["mcpServers"] = {}

    config["mcpServers"]["agent-drive"] = {
        "command": command,
        "args": args,
        "env": {
            "AGENT_DRIVE_URL": api_url,
        },
    }

    config_path.write_text(json.dumps(config, indent=2))


@app.command()
def install(
    method: str = typer.Option("uvx", help="Install method: uvx, pipx, or pip"),
):
    """Full setup: authenticate + configure Claude Code MCP."""
    api_url = _get_api_url()

    # Step 1: Login
    _do_login(api_url)

    # Step 2: Write MCP config
    typer.echo("\n  Configuring Claude Code MCP...")
    _write_mcp_config(method, api_url)

    # Step 3: Validate
    creds = load_credentials()
    if creds:
        with httpx.Client(timeout=10) as client:
            try:
                resp = client.get(
                    f"{api_url}/health",
                    headers={"Authorization": f"Bearer {creds['api_key']}"},
                )
                if resp.status_code == 200:
                    typer.echo("  Connection verified.")
            except httpx.ConnectError:
                typer.echo("  Warning: could not verify connection (server may not be reachable).")

    typer.echo("\n  ✓ Agent Drive installed. Restart Claude Code to use.")


@app.command()
def serve():
    """Start the MCP stdio server (called by Claude Code)."""
    import asyncio
    from agentdrive_mcp.server import main
    asyncio.run(main())


@app.command()
def login():
    """Authenticate with Agent Drive (re-login)."""
    api_url = _get_api_url()
    _do_login(api_url)
    typer.echo("  Ready to use!")


@app.command()
def status():
    """Show current authentication and config status."""
    creds = load_credentials()
    if not creds:
        typer.echo("Not logged in. Run 'agentdrive-mcp login' to authenticate.")
        raise typer.Exit(1)
    typer.echo(f"  Email:     {creds['email']}")
    typer.echo(f"  Tenant:    {creds['tenant_id']}")
    typer.echo(f"  Key:       {creds['api_key'][:14]}...")
    typer.echo(f"  Since:     {creds.get('created_at', 'unknown')}")

    # Check MCP config
    config_path = Path.home() / ".claude.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        if "mcpServers" in config and "agent-drive" in config["mcpServers"]:
            typer.echo("  MCP:       configured in ~/.claude.json")
        else:
            typer.echo("  MCP:       not configured (run 'agentdrive-mcp install')")
    else:
        typer.echo("  MCP:       ~/.claude.json not found")


if __name__ == "__main__":
    app()
