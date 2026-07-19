#!/usr/bin/env python3
"""Validate the Render staging Blueprint before applying it."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only outside the dev environment
    yaml = None


PLACEHOLDER_PATTERN = re.compile(r"<[A-Z0-9_]+>")
DIGEST_PATTERN = re.compile(r"@sha256:[a-fA-F0-9]{64}$")
EXPECTED_SERVICES = {
    "dealhunter-staging-api": "web",
    "dealhunter-staging-web": "web",
    "dealhunter-staging-redis": "keyvalue",
}
EXPECTED_DATABASES = {"dealhunter-staging-postgres"}


def fail(message: str) -> None:
    print(f"staging_provisioning_validation=error: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_blueprint(path: Path) -> tuple[str, dict[str, Any]]:
    if yaml is None:
        fail("PyYAML is required. Run this with the backend virtual environment.")

    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        fail("render.yaml must parse to a YAML object")
    return raw, data


def env_map(service: dict[str, Any]) -> dict[str, dict[str, Any]]:
    env_vars = service.get("envVars", [])
    if not isinstance(env_vars, list):
        fail(f"{service.get('name')} envVars must be a list")

    mapped: dict[str, dict[str, Any]] = {}
    for item in env_vars:
        if not isinstance(item, dict) or not isinstance(item.get("key"), str):
            fail(f"{service.get('name')} has an invalid env var entry")
        mapped[item["key"]] = item
    return mapped


def service_by_name(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    services = data.get("services")
    if not isinstance(services, list):
        fail("services must be a list")

    mapped: dict[str, dict[str, Any]] = {}
    for service in services:
        if not isinstance(service, dict):
            fail("each service must be an object")
        name = service.get("name")
        if not isinstance(name, str):
            fail("each service must have a name")
        mapped[name] = service
    return mapped


def validate_services(
    services: dict[str, dict[str, Any]], allow_placeholders: bool
) -> None:
    missing = set(EXPECTED_SERVICES) - set(services)
    if missing:
        fail(f"missing services: {', '.join(sorted(missing))}")

    for name, expected_type in EXPECTED_SERVICES.items():
        service = services[name]
        if service.get("type") != expected_type:
            fail(f"{name} must be type {expected_type}")

    for name in (
        "dealhunter-staging-api",
        "dealhunter-staging-web",
    ):
        service = services[name]
        if service.get("runtime") != "image":
            fail(f"{name} must use runtime: image")

        image = service.get("image")
        if not isinstance(image, dict) or not isinstance(image.get("url"), str):
            fail(f"{name} must define image.url")

        creds = image.get("creds")
        registry_creds = (
            creds.get("fromRegistryCreds") if isinstance(creds, dict) else None
        )
        if (
            not isinstance(registry_creds, dict)
            or registry_creds.get("name") != "ghcr-saveiq"
        ):
            fail(f"{name} must use the ghcr-saveiq registry credential")

        image_url = image["url"]
        if "@sha256:" not in image_url:
            fail(f"{name} image must be pinned by sha256 digest")
        if not allow_placeholders and not DIGEST_PATTERN.search(image_url):
            fail(f"{name} image digest must be a 64-character sha256 digest")


def validate_env(services: dict[str, dict[str, Any]]) -> None:
    api_env = env_map(services["dealhunter-staging-api"])
    web_env = env_map(services["dealhunter-staging-web"])

    api_command = services["dealhunter-staging-api"].get("dockerCommand")
    if api_command != "python -m app.server":
        fail("API service must use the Render-friendly Python startup entrypoint")

    admin_token = api_env.get("ADMIN_API_TOKEN")
    if admin_token is None or admin_token.get("sync") is not False:
        fail("ADMIN_API_TOKEN must be sync: false")

    if (
        api_env.get("DATABASE_URL", {}).get("fromDatabase", {}).get("name")
        != "dealhunter-staging-postgres"
    ):
        fail("API DATABASE_URL must come from dealhunter-staging-postgres")

    if (
        api_env.get("REDIS_URL", {}).get("fromService", {}).get("name")
        != "dealhunter-staging-redis"
    ):
        fail("API REDIS_URL must come from dealhunter-staging-redis")

    if web_env.get("STAGING_NOINDEX", {}).get("value") != "true":
        fail("web service must set STAGING_NOINDEX=true")

    if web_env.get("NEXT_PUBLIC_BRAND_NAME", {}).get("value") != "DealHunter":
        fail("web service must set NEXT_PUBLIC_BRAND_NAME=DealHunter")


def validate_database(data: dict[str, Any]) -> None:
    databases = data.get("databases")
    if not isinstance(databases, list):
        fail("databases must be a list")

    names = {
        database.get("name") for database in databases if isinstance(database, dict)
    }
    missing = EXPECTED_DATABASES - names
    if missing:
        fail(f"missing databases: {', '.join(sorted(missing))}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("blueprint", type=Path)
    parser.add_argument("--allow-placeholders", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raw, data = load_blueprint(args.blueprint)

    if not args.allow_placeholders and PLACEHOLDER_PATTERN.search(raw):
        fail("replace all <PLACEHOLDER> values before applying the Blueprint")

    services = service_by_name(data)
    validate_services(services, allow_placeholders=args.allow_placeholders)
    validate_env(services)
    validate_database(data)

    if args.allow_placeholders:
        print("staging_provisioning_template_validation=ok")
    else:
        print("staging_provisioning_validation=ok")


if __name__ == "__main__":
    main()
