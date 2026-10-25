#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Build and run Building Comfort with matching local ComputationGraph artifacts."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request


TUTORIAL = Path(__file__).resolve().parents[1]
WORKSPACE = TUTORIAL.parents[2]
INSTANCE = "building-comfort-server"
PLUGINS = (
    "drasi-source-postgres",
    "drasi-bootstrap-postgres",
    "drasi-reaction-dashboard",
    "drasi-reaction-log",
)
QUERIES = (
    "building-comfort-ui", "building-comfort-level-calc",
    "floor-comfort-level-calc", "room-alert", "floor-alert", "building-alert",
)


def load_environment():
    path = TUTORIAL / ".env"
    if path.exists():
        for number, line in enumerate(path.read_text().splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
                raise ValueError(f"{path}:{number}: expected NAME=value")
            os.environ.setdefault(key, value.strip().strip("'\""))
    os.environ["DRASI_TUTORIAL_DIR"] = str(TUTORIAL)
    os.environ.setdefault("COMPOSE_PROJECT_NAME", "building-comfort-cg")
    project = os.environ["COMPOSE_PROJECT_NAME"]
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,50}", project):
        raise ValueError("COMPOSE_PROJECT_NAME must be a lowercase project name")
    os.environ.setdefault("POSTGRES_PORT", os.environ.get("POSTGRES_HOST_PORT", "5732"))
    os.environ.setdefault("POSTGRES_HOST_PORT", os.environ["POSTGRES_PORT"])
    if os.environ["POSTGRES_PORT"] != os.environ["POSTGRES_HOST_PORT"]:
        raise ValueError("POSTGRES_PORT and POSTGRES_HOST_PORT must match")
    os.environ.setdefault("SERVER_HOST", "127.0.0.1")
    os.environ.setdefault("DASHBOARD_HOST", "127.0.0.1")


def runtime_dir():
    return Path(os.environ.get("DRASI_DEMO_DIR", TUTORIAL / ".runtime")).resolve()


def run(argv, *, capture=False, stdin=None, cwd=TUTORIAL):
    print("+", " ".join(map(str, argv)), flush=True)
    return subprocess.run(
        list(map(str, argv)), cwd=cwd, check=True, text=True, input=stdin,
        stdout=subprocess.PIPE if capture else None,
    ).stdout


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build():
    server = Path(os.environ.get("DRASI_SERVER_REPO", WORKSPACE / "drasi-server")).resolve()
    core = server.parent / "drasi-core"
    manifest = server / "Cargo.toml"
    if not manifest.is_file() or not (core / "lib/Cargo.toml").is_file():
        raise RuntimeError(
            "Build requires existing sibling drasi-server/ and drasi-core/ checkouts. "
            "Use their ComputationGraph branches; this script does not clone or switch branches."
        )
    dependency = tomllib.loads(manifest.read_text())["dependencies"]["drasi-lib"]
    if "path" not in dependency or (server / dependency["path"]).resolve() != core / "lib":
        raise RuntimeError("Server must use the sibling drasi-core/lib path dependency")
    state = runtime_dir()
    if (state / "server.lock").exists():
        raise RuntimeError("Stop this demo before rebuilding; server.lock is present")
    target = Path(os.environ.get("CARGO_TARGET_DIR", server / "target")).resolve()
    common = ["--locked", "--target-dir", target]
    run(["cargo", "build", "--manifest-path", manifest, *common, "--bin", "drasi-server"],
        cwd=server)
    packages = [item for package in PLUGINS for item in ("-p", package)]
    run(["cargo", "build", "--manifest-path", core / "Cargo.toml", *common,
         *packages, "--lib", "--features", "dynamic-plugin"], cwd=core)
    extension = ".dll" if sys.platform == "win32" else ".dylib" if sys.platform == "darwin" else ".so"
    prefix = "" if sys.platform == "win32" else "lib"
    binary = "drasi-server.exe" if sys.platform == "win32" else "drasi-server"
    files = {"server": target / "debug" / binary}
    files.update({package: target / "debug" / (prefix + package.replace("-", "_") + extension)
                  for package in PLUGINS})
    # Copy a complete, versioned set rather than loading whichever libraries
    # happen to be present in the shared Cargo target or global plugin cache.
    hashes = {name: sha256(path) for name, path in files.items()}
    identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    bundle = state / "builds" / identity
    (bundle / "plugins").mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for name, source in files.items():
        destination = (bundle if name == "server" else bundle / "plugins") / source.name
        if not destination.exists():
            shutil.copy2(source, destination)
        if sha256(destination) != hashes[name]:
            raise RuntimeError(f"Artifact copy/hash mismatch: {destination}")
        artifacts[name] = {"path": str(destination), "sha256": hashes[name]}
    provenance = {
        "runtime": "computationGraph", "artifacts": artifacts,
        "rustc": run(["rustc", "--version"], capture=True).strip(),
        "repositories": {
            name: {
                "revision": run(["git", "-C", path, "rev-parse", "HEAD"], capture=True).strip(),
                "status": run(["git", "-C", path, "status", "--short"], capture=True),
            } for name, path in (("drasi-server", server), ("drasi-core", core))
        },
    }
    temporary = state / "build.json.tmp"
    temporary.write_text(json.dumps(provenance, indent=2) + "\n")
    temporary.replace(state / "build.json")
    print(f"Built Server and all four plugins. Build record: {state / 'build.json'}")


def verified_build():
    path = runtime_dir() / "build.json"
    if not path.is_file():
        raise RuntimeError("No local build record. Run python3 scripts/demo.py build first.")
    record = json.loads(path.read_text())
    if record["runtime"] != "computationGraph":
        raise RuntimeError("Build record does not identify the ComputationGraph runtime")
    artifacts = record["artifacts"]
    if set(artifacts) != {"server", *PLUGINS}:
        raise RuntimeError("Build record must contain Server and exactly the four required plugins")
    for artifact in artifacts.values():
        path = Path(artifact["path"])
        if not path.is_file() or sha256(path) != artifact["sha256"]:
            raise RuntimeError(f"Missing or changed local artifact: {path}; rebuild the demo")
    plugins = Path(artifacts[PLUGINS[0]]["path"]).parent
    expected = {Path(artifacts[name]["path"]) for name in PLUGINS}
    if set(plugins.iterdir()) != expected:
        raise RuntimeError(f"Unexpected files in the private plugin directory: {plugins}")
    return Path(artifacts["server"]["path"]), plugins


def engine():
    executable = os.environ.get("CONTAINER_ENGINE", "podman")
    if executable not in ("podman", "docker"):
        raise ValueError("CONTAINER_ENGINE must be podman or docker")
    if not shutil.which(executable):
        raise RuntimeError(f"{executable} is not installed; install it or set CONTAINER_ENGINE")
    return executable


def compose(*arguments):
    return run([engine(), "compose", "-p", os.environ["COMPOSE_PROJECT_NAME"],
                "-f", TUTORIAL / "database/docker-compose.yml", *arguments])


def container():
    return os.environ["COMPOSE_PROJECT_NAME"] + "-postgres"


def check_database_ownership():
    project = os.environ["COMPOSE_PROJECT_NAME"]
    # Never reuse/remove an older tutorial's database or a same-name resource
    # without this tutorial's ownership label.
    resources = (
        ("container", container(), "ps"),
        ("volume", project + "_building_comfort_postgres_data", "volume"),
    )
    for kind, name, listing in resources:
        argv = [engine(), "ps", "-a", "--format", "{{.Names}}"] if listing == "ps" else [
            engine(), "volume", "ls", "--format", "{{.Name}}"]
        names = run(argv, capture=True).splitlines()
        if name not in names:
            continue
        information = json.loads(run([engine(), kind, "inspect", name], capture=True))[0]
        labels = information.get("Labels") if kind == "volume" else information["Config"]["Labels"]
        if not labels or labels.get("io.drasi.building-comfort.path") != str(TUTORIAL):
            raise RuntimeError(f"Refusing to reuse or remove unowned {kind}: {name}")


def sql(statement, *, admin=False):
    return run([engine(), "exec", "-i", container(), "psql", "-X", "-v", "ON_ERROR_STOP=1",
                "-U", "postgres" if admin else "drasi_user", "-d", "building_comfort",
                "-At"], stdin=statement, capture=True).strip()


def database():
    check_database_ownership()
    image = "docker.io/library/postgres:14-alpine"
    inspected = subprocess.run([engine(), "image", "inspect", image],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if inspected.returncode:
        # Let Podman use its own registry configuration, not a Compose
        # provider's possibly stale Docker Desktop credential helper.
        run([engine(), "pull", image])
    compose("up", "-d")
    deadline = time.monotonic() + 90
    while True:
        result = subprocess.run(
            [engine(), "exec", container(), "pg_isready", "-U", "postgres", "-d", "building_comfort"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError(f"PostgreSQL did not become ready; inspect {container()}'s logs")
        time.sleep(1)
    tables = sql("SELECT count(*) FROM pg_tables WHERE schemaname='public';", admin=True)
    if tables == "0":
        print(sql((TUTORIAL / "database/init.sql").read_text(), admin=True))
    else:
        required = sql(
            """SELECT count(*) FROM pg_tables WHERE schemaname='public'
               AND tablename IN ('Building','Floor','Room');""", admin=True)
        if required != "3":
            raise RuntimeError("Existing database has an unexpected schema; it was not reset")
        print("Keeping the existing building and sensor readings; no reseed.")
    if sql("SELECT count(*) FROM pg_publication WHERE pubname='drasi_building_comfort_pub';") != "1":
        raise RuntimeError("Required PostgreSQL publication is missing")
    print(sql('SELECT id, temperature, humidity, co2 FROM "Room" ORDER BY id;'))


def cleanup(remove_volumes=False):
    if (runtime_dir() / "server.lock").exists():
        raise RuntimeError("Stop the foreground Server with Ctrl+C before database cleanup")
    check_database_ownership()
    compose("down", *(["--volumes"] if remove_volumes else []))
    print("Database removed." if remove_volumes else "Database stopped; its volume is preserved.")


def room_id(value):
    if not re.fullmatch(r"[A-Za-z0-9_]+", value):
        raise ValueError("Room ID must contain only letters, digits, and underscores")
    return value


def set_room(identifier, temperature, humidity, co2):
    result = sql(
        f"""UPDATE "Room" SET temperature={int(temperature)}, humidity={int(humidity)},
            co2={int(co2)} WHERE id='{room_id(identifier)}' RETURNING id;""")
    if result.splitlines() != [identifier, "UPDATE 1"]:
        raise RuntimeError(f"Expected to update exactly room {identifier}; PostgreSQL returned {result!r}")
    print(f"{identifier}: temperature={temperature}, humidity={humidity}, co2={co2}")


def reset_room(identifier=None):
    if identifier:
        set_room(identifier, 70, 40, 10)
    else:
        print(sql('UPDATE "Room" SET temperature=70, humidity=40, co2=10;'))


def simulate(interval, count=None):
    if interval <= 0 or (count is not None and count <= 0):
        raise ValueError("Simulation interval and count must be positive")
    rooms = sql('SELECT id FROM "Room" ORDER BY id;').splitlines()
    if not rooms:
        raise RuntimeError("No rooms to simulate")
    iteration = 0
    while count is None or iteration < count:
        set_room(random.choice(rooms), random.randint(55, 85),
                 random.randint(20, 55), random.randint(5, 904))
        iteration += 1
        if count is None or iteration < count:
            time.sleep(interval)


def get_json(url):
    with urllib.request.urlopen(url, timeout=3) as response:
        return json.load(response)


def api_url():
    return f"http://127.0.0.1:{os.environ.get('SERVER_PORT', '8380')}/api/v1/instances/{INSTANCE}"


def check():
    proof = get_json(api_url() + "/runtime")
    if proof.get("success") is not True or proof.get("data") != {
        "instanceId": INSTANCE, "runtime": "computationGraph", "running": True,
    }:
        raise RuntimeError(f"Expected this instance's running ComputationGraph, got {proof}")
    for kind, expected in (
        ("sources", {"building-facilities"}),
        ("queries", set(QUERIES)),
        ("reactions", {"building-comfort-dashboard", "console-log"}),
    ):
        response = get_json(api_url() + "/" + kind)
        if response.get("success") is not True:
            raise RuntimeError(f"{kind} inspection failed: {response}")
        components = response["data"]
        identities = {component["id"] for component in components}
        allowed = expected | ({"__component_graph__"} if kind == "sources" else set())
        if not expected <= identities or not identities <= allowed:
            raise RuntimeError(f"Unexpected {kind}: {components}")
        if any(component["status"].lower() != "running" for component in components):
            raise RuntimeError(f"Not all {kind} are running: {components}")
    dashboard = f"http://127.0.0.1:{os.environ.get('DASHBOARD_PORT', '3000')}"
    dashboards = get_json(dashboard + "/api/dashboards")
    if not any(item["id"] == "building-comfort" for item in dashboards):
        raise RuntimeError(f"Building Comfort dashboard is not available: {dashboards}")
    return proof


def start():
    binary, plugins = verified_build()
    state = runtime_dir()
    lock = state / "server.lock"
    environment = dict(os.environ, DRASI_PLUGINS_DIR=str(plugins))
    config = Path(os.environ.get("CONFIG_FILE", TUTORIAL / "server-config.yaml")).resolve()
    if not config.is_file():
        raise RuntimeError(f"Configuration not found: {config}")
    with lock.open("x") as stream:
        stream.write(f"{os.getpid()}\n")
    process = None
    old_term = signal.getsignal(signal.SIGTERM)
    try:
        for host, port in (
            (environment["SERVER_HOST"], environment.get("SERVER_PORT", "8380")),
            (environment["DASHBOARD_HOST"], environment.get("DASHBOARD_PORT", "3000")),
        ):
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind((host, int(port)))
                probe.listen(1)
        # Only this private, hash-checked local build bypasses registry signing.
        process = subprocess.Popen(
            [str(binary), "--config", str(config), "--plugins-dir", str(plugins),
             "--skip-verification"], cwd=state, env=environment,
        )
        signal.signal(signal.SIGTERM, lambda *_: process.send_signal(signal.SIGINT))
        deadline = time.monotonic() + 120
        while True:
            if process.poll() is not None:
                raise RuntimeError(f"Server exited during startup: {process.returncode}")
            try:
                proof = check()
                break
            except (urllib.error.URLError, TimeoutError, RuntimeError) as error:
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"Demo readiness timed out: {error}") from error
                time.sleep(0.5)
        (state / "runtime.json").write_text(json.dumps(proof, indent=2) + "\n")
        print(f"\nBuilding Comfort READY: ComputationGraph; source, six queries and two reactions running."
              f"\nDashboard: http://localhost:{os.environ.get('DASHBOARD_PORT', '3000')}"
              "\nPress Ctrl+C to stop Server. PostgreSQL data is preserved.", flush=True)
        code = process.wait()
        if code:
            raise RuntimeError(f"Server exited with status {code}")
    finally:
        signal.signal(signal.SIGTERM, old_term)
        try:
            if process is not None and process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired as error:
                    process.kill()
                    process.wait()
                    raise RuntimeError("Server needed forced shutdown after 30 seconds") from error
        finally:
            lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for name in ("build", "verify-build", "database", "start", "start-demo", "check"):
        commands.add_parser(name)
    clean = commands.add_parser("cleanup")
    clean.add_argument("--volumes", action="store_true", help="Explicitly delete this demo's database volume")
    broken = commands.add_parser("break-room")
    broken.add_argument("room")
    reset = commands.add_parser("reset-room")
    reset.add_argument("room", nargs="?")
    change = commands.add_parser("set-room")
    change.add_argument("room")
    for name in ("temperature", "humidity", "co2"):
        change.add_argument(name, type=int)
    simulation = commands.add_parser("simulate")
    simulation.add_argument("interval", type=float, nargs="?", default=3)
    simulation.add_argument("--count", type=int, help="Stop after this many changes")
    args = parser.parse_args()
    try:
        load_environment()
        if args.action == "build":
            build()
        elif args.action == "verify-build":
            verified_build()
        elif args.action == "database":
            database()
        elif args.action == "start-demo":
            verified_build()
            database()
            start()
        elif args.action == "start":
            start()
        elif args.action == "check":
            print(json.dumps(check(), indent=2))
        elif args.action == "cleanup":
            cleanup(args.volumes)
        elif args.action == "break-room":
            set_room(args.room, 40, 20, 700)
        elif args.action == "reset-room":
            reset_room(args.room)
        elif args.action == "set-room":
            set_room(args.room, args.temperature, args.humidity, args.co2)
        elif args.action == "simulate":
            simulate(args.interval, args.count)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError,
            urllib.error.URLError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
