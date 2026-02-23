#!/usr/bin/env python3
"""Developer CLI for local workflows in the board-third-party-lib repository.

This script is the primary developer automation entry point for:
- bootstrap/setup (`bootstrap`)
- dependency lifecycle (`up`, `down`, `status`)
- backend testing (`test`)
- environment diagnostics (`doctor`)
- local PostgreSQL backup/restore helpers (`db-backup`, `db-restore`)

Use `python ./scripts/dev.py --help` and `python ./scripts/dev.py <command> --help`
for command-specific help.
"""

from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class DevConfig:
    """Configuration values used across CLI commands.

    Attributes:
        repo_root: Repository root directory.
        compose_file: Relative path to the Docker Compose file.
        postgres_container_name: Expected local PostgreSQL container name.
        postgres_user: PostgreSQL username for local commands.
        postgres_database: PostgreSQL database name for local commands.
        backend_project: Relative path to the backend API project file.
        backend_solution: Relative path to the backend solution file.
    """

    repo_root: Path
    compose_file: str
    postgres_container_name: str
    postgres_user: str
    postgres_database: str
    backend_project: str
    backend_solution: str


class DevCliError(RuntimeError):
    """Raised for expected CLI/runtime failures with user-friendly messages."""


def write_step(message: str) -> None:
    """Print a visible step marker for long-running actions.

    Args:
        message: Human-readable step description to print.

    Returns:
        None.
    """

    print(f"==> {message}")


def quote_cmd(parts: Sequence[str]) -> str:
    """Render a subprocess command as a shell-like string for error messages.

    Args:
        parts: Command tokens to quote and join.

    Returns:
        A shell-safe string representation of the command.
    """

    return " ".join(shlex.quote(p) for p in parts)


def run_command(
    cmd: Sequence[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    capture_output: bool = False,
    text: bool = True,
    stdin=None,
    stdout=None,
    stderr=None,
) -> subprocess.CompletedProcess:
    """Run a subprocess command with consistent error handling.

    Args:
        cmd: Command and arguments to execute.
        cwd: Optional working directory for the subprocess.
        check: When True, raise an error on non-zero exit code.
        capture_output: When True, capture stdout/stderr into the result.
        text: When True, use text mode for subprocess I/O.
        stdin: Optional stdin stream or data source for the subprocess.
        stdout: Optional stdout destination override.
        stderr: Optional stderr destination override.

    Returns:
        The completed subprocess result.

    Raises:
        DevCliError: If ``check`` is True and the command exits non-zero.
    """

    result = subprocess.run(
        list(cmd),
        cwd=str(cwd) if cwd else None,
        check=False,
        capture_output=capture_output,
        text=text,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
    )
    if check and result.returncode != 0:
        raise DevCliError(f"Command failed ({result.returncode}): {quote_cmd(list(cmd))}")
    return result


def assert_command_available(name: str) -> None:
    """Ensure a required executable exists on PATH.

    Args:
        name: Executable name to look up on ``PATH``.

    Returns:
        None.

    Raises:
        DevCliError: If the command is not available on ``PATH``.
    """

    if shutil.which(name) is None:
        raise DevCliError(f"Required command '{name}' was not found on PATH.")


def get_repo_root(script_path: Path) -> Path:
    """Resolve the repository root from this script path.

    Args:
        script_path: Path to this script file.

    Returns:
        The resolved repository root path.
    """

    return script_path.resolve().parent.parent


def test_submodule_initialized(path: Path) -> bool:
    """Return whether a git submodule appears initialized.

    Args:
        path: Submodule directory path.

    Returns:
        ``True`` when the submodule contains a `.git` entry, else ``False``.
    """

    return (path / ".git").exists()


def get_compose_args(config: DevConfig) -> list[str]:
    """Build docker compose base arguments for the configured compose file.

    Args:
        config: CLI configuration containing the compose file path.

    Returns:
        Base ``docker compose`` arguments including the ``-f`` compose file flag.
    """

    return ["compose", "-f", str(config.repo_root / config.compose_file)]


def invoke_docker_compose(config: DevConfig, sub_args: Sequence[str]) -> None:
    """Invoke docker compose with the configured compose file.

    Args:
        config: CLI configuration containing compose settings.
        sub_args: Additional ``docker compose`` arguments (for example ``["up", "-d"]``).

    Returns:
        None.

    Raises:
        DevCliError: If Docker is unavailable or the compose command fails.
    """

    assert_command_available("docker")
    args = ["docker", *get_compose_args(config), *sub_args]
    run_command(args, check=True, capture_output=False, text=True)


def get_docker_container_state(container_name: str) -> str | None:
    """Return Docker container state or ``None`` if the container is missing.

    Args:
        container_name: Docker container name to inspect.

    Returns:
        Container state string (for example ``"running"`` or ``"exited"``), or
        ``None`` when the container does not exist.

    Raises:
        DevCliError: If Docker is unavailable on ``PATH``.
    """

    assert_command_available("docker")
    result = run_command(
        ["docker", "container", "inspect", "-f", "{{.State.Status}}", container_name],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return (result.stdout or "").strip() or None


def wait_for_postgres(
    *,
    container_name: str,
    user: str,
    database: str,
    timeout_seconds: int = 60,
) -> None:
    """Wait until ``pg_isready`` succeeds inside the PostgreSQL container.

    Args:
        container_name: PostgreSQL container name.
        user: PostgreSQL user for readiness checks.
        database: PostgreSQL database for readiness checks.
        timeout_seconds: Maximum time to wait before failing.

    Returns:
        None.

    Raises:
        DevCliError: If PostgreSQL does not become ready before timeout.
    """

    write_step(f"Waiting for PostgreSQL readiness (up to {timeout_seconds} seconds)")
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        result = run_command(
            ["docker", "exec", container_name, "pg_isready", "-U", user, "-d", database],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("PostgreSQL is ready.")
            return
        time.sleep(2)
    raise DevCliError(f"Timed out waiting for PostgreSQL container '{container_name}' to become ready.")


def ensure_submodules(config: DevConfig) -> None:
    """Initialize backend/frontend submodules when needed.

    Args:
        config: CLI configuration containing the repository root.

    Returns:
        None.

    Raises:
        DevCliError: If Git is unavailable or submodule initialization fails.
    """

    assert_command_available("git")
    backend_path = config.repo_root / "backend"
    frontend_path = config.repo_root / "frontend"
    if test_submodule_initialized(backend_path) and test_submodule_initialized(frontend_path):
        print("Submodules appear initialized.")
        return

    write_step("Initializing submodules")
    run_command(["git", "submodule", "update", "--init", "--recursive"], cwd=config.repo_root)


def restore_backend(config: DevConfig) -> None:
    """Restore the backend solution.

    Args:
        config: CLI configuration containing backend solution paths.

    Returns:
        None.

    Raises:
        DevCliError: If ``dotnet`` is unavailable or restore fails.
    """

    assert_command_available("dotnet")
    backend_root = config.repo_root / "backend"
    solution_path = config.repo_root / config.backend_solution
    write_step("Restoring backend solution")
    run_command(["dotnet", "restore", str(solution_path)], cwd=backend_root)


def start_dependencies(config: DevConfig) -> None:
    """Start/reuse the local PostgreSQL dependency and wait until it is ready.

    Args:
        config: CLI configuration containing compose and PostgreSQL settings.

    Returns:
        None.

    Raises:
        DevCliError: If Docker/compose is unavailable, the compose file is missing,
            or PostgreSQL fails to start/become ready.
    """

    assert_command_available("docker")
    compose_full_path = config.repo_root / config.compose_file
    if not compose_full_path.exists():
        raise DevCliError(f"Compose file not found: {compose_full_path}")

    existing_state = get_docker_container_state(config.postgres_container_name)
    if existing_state == "running":
        write_step(f"Reusing existing PostgreSQL container '{config.postgres_container_name}' (already running)")
        wait_for_postgres(
            container_name=config.postgres_container_name,
            user=config.postgres_user,
            database=config.postgres_database,
        )
        return

    if existing_state is not None:
        write_step(
            f"Starting existing PostgreSQL container '{config.postgres_container_name}' "
            f"(state: {existing_state})"
        )
        run_command(["docker", "start", config.postgres_container_name])
        wait_for_postgres(
            container_name=config.postgres_container_name,
            user=config.postgres_user,
            database=config.postgres_database,
        )
        return

    write_step("Starting PostgreSQL via docker compose")
    invoke_docker_compose(config, ["up", "-d", "postgres"])
    wait_for_postgres(
        container_name=config.postgres_container_name,
        user=config.postgres_user,
        database=config.postgres_database,
    )


def stop_dependencies(config: DevConfig) -> None:
    """Stop docker compose dependencies while preserving named volumes.

    Args:
        config: CLI configuration containing compose and PostgreSQL settings.

    Returns:
        None.

    Raises:
        DevCliError: If the compose command fails.
    """

    write_step("Stopping PostgreSQL via docker compose")
    invoke_docker_compose(config, ["down"])
    remaining_state = get_docker_container_state(config.postgres_container_name)
    if remaining_state is not None:
        print(
            f"Note: container '{config.postgres_container_name}' still exists "
            "(likely not created by this compose project)."
        )
        print(f"Stop it manually if desired: docker stop {config.postgres_container_name}")


def show_status(config: DevConfig) -> None:
    """Show docker compose and PostgreSQL readiness status.

    Args:
        config: CLI configuration containing compose and PostgreSQL settings.

    Returns:
        None.
    """

    write_step("docker compose status")
    invoke_docker_compose(config, ["ps"])

    state = get_docker_container_state(config.postgres_container_name)
    if state is None:
        print(f"Container '{config.postgres_container_name}' was not found.")
        return

    write_step("Named PostgreSQL container status")
    print(f"{config.postgres_container_name} : {state}")

    write_step("PostgreSQL readiness")
    result = run_command(
        [
            "docker",
            "exec",
            config.postgres_container_name,
            "pg_isready",
            "-U",
            config.postgres_user,
            "-d",
            config.postgres_database,
        ],
        check=False,
        capture_output=False,
        text=True,
    )
    if result.returncode != 0:
        print("Warning: PostgreSQL container is not ready (or container is not running).")


def run_backend_api(config: DevConfig, *, do_restore: bool) -> None:
    """Run the backend API project, optionally restoring first.

    Args:
        config: CLI configuration containing backend project paths.
        do_restore: Whether to run ``dotnet restore`` before starting the API.

    Returns:
        None.

    Raises:
        DevCliError: If ``dotnet`` is unavailable, the project file is missing,
            or restore/run commands fail.
    """

    assert_command_available("dotnet")
    backend_root = config.repo_root / "backend"
    project_path = config.repo_root / config.backend_project
    if not project_path.exists():
        raise DevCliError(f"Backend project not found: {project_path}")

    if do_restore:
        write_step("Restoring backend project")
        run_command(["dotnet", "restore", str(project_path)], cwd=backend_root)

    write_step("Starting backend API (Ctrl+C to stop)")
    run_command(["dotnet", "run", "--project", str(project_path)], cwd=backend_root, check=True)


def run_tests(config: DevConfig, *, run_integration: bool) -> None:
    """Run backend unit tests and optionally integration tests.

    Args:
        config: CLI configuration containing backend test project paths.
        run_integration: Whether to run integration tests after unit tests.

    Returns:
        None.

    Raises:
        DevCliError: If ``dotnet`` is unavailable or any required test command fails.
    """

    assert_command_available("dotnet")
    backend_root = config.repo_root / "backend"
    unit_project = config.repo_root / "backend/tests/Board.ThirdPartyLibrary.Api.Tests/Board.ThirdPartyLibrary.Api.Tests.csproj"
    integration_project = (
        config.repo_root
        / "backend/tests/Board.ThirdPartyLibrary.Api.IntegrationTests/Board.ThirdPartyLibrary.Api.IntegrationTests.csproj"
    )

    write_step("Running backend unit tests")
    run_command(
        ["dotnet", "test", str(unit_project), "--filter", "Category!=Integration"],
        cwd=backend_root,
    )

    if run_integration:
        write_step("Running backend integration tests (Docker/Testcontainers required)")
        run_command(
            ["dotnet", "test", str(integration_project), "--filter", "Category=Integration"],
            cwd=backend_root,
        )
    else:
        print("Skipping integration tests.")


def run_doctor(config: DevConfig) -> None:
    """Run environment diagnostics for local tooling and repo state.

    Args:
        config: CLI configuration containing repository and compose settings.

    Returns:
        None.
    """

    issues: list[str] = []

    write_step("Environment checks")
    for cmd in ("git", "docker", "dotnet", "python"):
        if shutil.which(cmd):
            print(f"Found: {cmd}")
        else:
            print(f"Missing command: {cmd}")
            issues.append(f"Required command missing from PATH: {cmd}")

    backend_path = config.repo_root / "backend"
    frontend_path = config.repo_root / "frontend"
    if not test_submodule_initialized(backend_path):
        issues.append("Backend submodule is not initialized (run: git submodule update --init --recursive)")
    if not test_submodule_initialized(frontend_path):
        issues.append("Frontend submodule is not initialized (run: git submodule update --init --recursive)")

    if shutil.which("git"):
        write_step("Submodule status")
        run_command(["git", "submodule", "status"], cwd=config.repo_root, check=False, capture_output=False)

    if shutil.which("dotnet"):
        write_step(".NET SDK version")
        result = run_command(["dotnet", "--version"], check=False, capture_output=False)
        if result.returncode != 0:
            issues.append("dotnet is installed but `dotnet --version` failed")

    if shutil.which("docker"):
        write_step("Docker version")
        result = run_command(["docker", "--version"], check=False, capture_output=False)
        if result.returncode != 0:
            issues.append("docker is installed but `docker --version` failed")
        write_step("Docker Compose version")
        result = run_command(["docker", "compose", "version"], check=False, capture_output=False)
        if result.returncode != 0:
            issues.append("Docker Compose is unavailable (`docker compose version` failed)")
        daemon_check = run_command(["docker", "info"], check=False, capture_output=True, text=True)
        if daemon_check.returncode != 0:
            issues.append("Docker daemon is not reachable (start Docker Desktop/Engine)")

    compose_full_path = config.repo_root / config.compose_file
    if compose_full_path.exists():
        print(f"Compose file found: {compose_full_path}")
    else:
        print(f"Compose file missing: {compose_full_path}")
        issues.append(f"Compose file not found: {compose_full_path}")

    print()
    write_step("Doctor summary")
    if issues:
        print(f"FAIL ({len(issues)} issue(s) detected)")
        for idx, issue in enumerate(issues, start=1):
            print(f"{idx}. {issue}")
        print()
        print("Suggested next steps:")
        print("  python ./scripts/dev.py bootstrap")
        print("  python ./scripts/dev.py up")
    else:
        print("PASS (no issues detected)")
        print()
        print("Suggested next steps:")
        print("  python ./scripts/dev.py bootstrap")
        print("  python ./scripts/dev.py up")


def ensure_postgres_running_for_db_ops(config: DevConfig) -> None:
    """Ensure PostgreSQL is running before DB helper commands execute.

    Args:
        config: CLI configuration containing PostgreSQL container settings.

    Returns:
        None.

    Raises:
        DevCliError: If the configured PostgreSQL container is not running or
            readiness checks fail.
    """

    state = get_docker_container_state(config.postgres_container_name)
    if state != "running":
        raise DevCliError(
            f"PostgreSQL container '{config.postgres_container_name}' is not running. "
            "Start it first with 'python ./scripts/dev.py up --dependencies-only' (or 'up')."
        )
    wait_for_postgres(
        container_name=config.postgres_container_name,
        user=config.postgres_user,
        database=config.postgres_database,
    )


def default_backup_path(repo_root: Path, database_name: str) -> Path:
    """Build a timestamped default SQL backup path inside ``./backups/``.

    Args:
        repo_root: Repository root directory.
        database_name: Database name to include in the filename.

    Returns:
        A timestamped SQL backup file path under ``<repo_root>/backups``.
    """

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return repo_root / "backups" / f"{database_name}-{timestamp}.sql"


def db_backup(config: DevConfig, *, output_path: Path | None) -> None:
    """Create a SQL backup using ``pg_dump`` from the Dockerized PostgreSQL instance.

    Args:
        config: CLI configuration containing PostgreSQL container settings.
        output_path: Optional explicit backup output path. When ``None``, a
            timestamped path under ``./backups`` is generated.

    Returns:
        None.

    Raises:
        DevCliError: If Docker is unavailable, PostgreSQL is not running/ready,
            or the backup command fails.
    """

    assert_command_available("docker")
    ensure_postgres_running_for_db_ops(config)

    target = (output_path or default_backup_path(config.repo_root, config.postgres_database)).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    write_step(f"Backing up database '{config.postgres_database}' to {target}")
    cmd = [
        "docker",
        "exec",
        config.postgres_container_name,
        "pg_dump",
        "-U",
        config.postgres_user,
        "-d",
        config.postgres_database,
        "--format=plain",
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        "--encoding=UTF8",
    ]

    with target.open("wb") as out_file:
        result = subprocess.run(cmd, stdout=out_file, stderr=subprocess.PIPE, check=False)

    if result.returncode != 0:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        stderr_text = (result.stderr or b"").decode(errors="replace").strip()
        raise DevCliError(
            f"Database backup failed ({result.returncode}): {quote_cmd(cmd)}"
            + (f"\n{stderr_text}" if stderr_text else "")
        )

    print(f"Backup complete: {target}")


def db_restore(config: DevConfig, *, input_path: Path) -> None:
    """Restore a SQL backup into the configured database using ``psql``.

    Args:
        config: CLI configuration containing PostgreSQL container settings.
        input_path: Path to the SQL backup file to restore.

    Returns:
        None.

    Raises:
        DevCliError: If the backup file is missing, Docker is unavailable,
            PostgreSQL is not running/ready, or the restore command fails.
    """

    assert_command_available("docker")
    source = input_path.resolve()
    if not source.exists():
        raise DevCliError(f"Backup file not found: {source}")

    ensure_postgres_running_for_db_ops(config)
    write_step(f"Restoring database '{config.postgres_database}' from {source}")
    cmd = [
        "docker",
        "exec",
        "-i",
        config.postgres_container_name,
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        config.postgres_user,
        "-d",
        config.postgres_database,
    ]

    with source.open("rb") as in_file:
        result = subprocess.run(cmd, stdin=in_file, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

    if result.returncode != 0:
        stderr_text = (result.stderr or b"").decode(errors="replace").strip()
        raise DevCliError(
            f"Database restore failed ({result.returncode}): {quote_cmd(cmd)}"
            + (f"\n{stderr_text}" if stderr_text else "")
        )

    print("Restore complete.")


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI parser with typed subcommands and shared options.

    Args:
        None.

    Returns:
        Configured top-level ``argparse.ArgumentParser`` instance.
    """

    parser = argparse.ArgumentParser(
        description="Developer automation CLI for local backend/API workflows.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "--compose-file",
        "-ComposeFile",
        default="backend/docker-compose.yml",
        help="Docker Compose file path",
    )
    shared.add_argument(
        "--postgres-container-name",
        "-PostgresContainerName",
        default="board_tpl_postgres",
        help="PostgreSQL container name",
    )
    shared.add_argument("--postgres-user", "-PostgresUser", default="board_tpl_user", help="PostgreSQL user")
    shared.add_argument(
        "--postgres-database",
        "-PostgresDatabase",
        default="board_tpl",
        help="PostgreSQL database name",
    )
    shared.add_argument(
        "--backend-project",
        "-BackendProject",
        default="backend/src/Board.ThirdPartyLibrary.Api/Board.ThirdPartyLibrary.Api.csproj",
        help="Backend API project path",
    )
    shared.add_argument(
        "--backend-solution",
        "-BackendSolution",
        default="backend/Board.ThirdPartyLibrary.Backend.sln",
        help="Backend solution path",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "bootstrap",
        parents=[shared],
        help="Initialize submodules and restore backend solution",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    up = subparsers.add_parser(
        "up",
        parents=[shared],
        help="Start/reuse PostgreSQL and run backend API",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    up.add_argument(
        "--bootstrap",
        "-Bootstrap",
        action="store_true",
        help="Run submodule initialization checks before startup",
    )
    up.add_argument(
        "--dependencies-only",
        "-DependenciesOnly",
        action="store_true",
        help="Start PostgreSQL only (do not run API)",
    )
    up.add_argument(
        "--skip-restore",
        "-SkipRestore",
        action="store_true",
        help="Skip dotnet restore before dotnet run",
    )

    subparsers.add_parser(
        "down",
        parents=[shared],
        help="Stop local dependencies via docker compose (preserves named volumes)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers.add_parser(
        "status",
        parents=[shared],
        help="Show docker compose and PostgreSQL readiness status",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    test = subparsers.add_parser(
        "test",
        parents=[shared],
        help="Run backend unit tests and optionally integration tests",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    test.add_argument("--skip-integration", "-SkipIntegration", action="store_true", help="Skip integration tests")

    subparsers.add_parser(
        "doctor",
        parents=[shared],
        help="Run local environment diagnostics",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    backup = subparsers.add_parser(
        "db-backup",
        parents=[shared],
        help="Create a SQL backup of the local PostgreSQL database",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    backup.add_argument(
        "output",
        nargs="?",
        type=Path,
        help="Output .sql path (defaults to ./backups/<db>-<utc-timestamp>.sql)",
    )

    restore = subparsers.add_parser(
        "db-restore",
        parents=[shared],
        help="Restore a SQL backup into the local PostgreSQL database",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    restore.add_argument("input", type=Path, help="Path to a .sql backup file created by db-backup")

    return parser


def config_from_args(args: argparse.Namespace, repo_root: Path) -> DevConfig:
    """Build ``DevConfig`` from parsed CLI arguments.

    Args:
        args: Parsed CLI arguments namespace.
        repo_root: Resolved repository root directory.

    Returns:
        A populated ``DevConfig`` instance.
    """

    return DevConfig(
        repo_root=repo_root,
        compose_file=args.compose_file,
        postgres_container_name=args.postgres_container_name,
        postgres_user=args.postgres_user,
        postgres_database=args.postgres_database,
        backend_project=args.backend_project,
        backend_solution=args.backend_solution,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """CLI program entry point.

    Args:
        argv: Optional argument list. When ``None``, uses ``sys.argv``.

    Returns:
        Process exit code (`0` for success, non-zero for failures).
    """

    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = get_repo_root(Path(__file__))
    config = config_from_args(args, repo_root)

    try:
        if args.command == "bootstrap":
            ensure_submodules(config)
            restore_backend(config)
            print("Bootstrap complete.")
        elif args.command == "up":
            if args.bootstrap:
                print("Running bootstrap checks before startup (convenience mode).")
                ensure_submodules(config)
            start_dependencies(config)
            if args.dependencies_only:
                print("Dependencies are up.")
                print("Run the API with: python ./scripts/dev.py up --skip-restore")
                return 0
            run_backend_api(config, do_restore=not args.skip_restore)
        elif args.command == "down":
            stop_dependencies(config)
            print("Dependencies stopped.")
        elif args.command == "status":
            show_status(config)
        elif args.command == "test":
            run_tests(config, run_integration=not args.skip_integration)
        elif args.command == "doctor":
            run_doctor(config)
        elif args.command == "db-backup":
            db_backup(config, output_path=args.output)
        elif args.command == "db-restore":
            db_restore(config, input_path=args.input)
        else:
            parser.error(f"Unknown command: {args.command}")
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
        return 130
    except DevCliError as ex:
        print(f"Error: {ex}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
