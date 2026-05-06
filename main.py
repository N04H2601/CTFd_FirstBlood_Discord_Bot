# -*- coding: utf-8 -*-
import asyncio
import contextlib
import csv
import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv


load_dotenv()

DEFAULT_CHECK_INTERVAL_SECONDS = 5.0
DEFAULT_ANNOUNCE_DELAY_SECONDS = 5.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 15.0
DEFAULT_SOLVE_FETCH_CONCURRENCY = 8
DEFAULT_DB_PATH = "first_bloods.sqlite3"
DEFAULT_DISPLAY_TIMEZONE = "Europe/Paris"
LEGACY_FIRST_BLOOD_FILE = "announced_first_bloods.csv"

LOGGER = logging.getLogger("firstblood")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class BotConfig:
    ctfd_api_key: str
    ctfd_api_base_url: str
    discord_channel_id: int
    discord_bot_token: str
    message_thumbnail: str | None
    check_interval_seconds: float
    announce_delay_seconds: float
    request_timeout_seconds: float
    solve_fetch_concurrency: int
    state_db_path: Path
    display_timezone: str
    ctfd_site_password: str | None

    @property
    def challenges_url(self) -> str:
        return f"{self.ctfd_api_base_url}/challenges"

    @property
    def request_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Token {self.ctfd_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @classmethod
    def from_env(cls) -> "BotConfig":
        return cls(
            ctfd_api_key=required_env("CTFD_API_KEY"),
            ctfd_api_base_url=normalize_ctfd_api_url(required_env("CTFD_API_URL")),
            discord_channel_id=env_int("DISCORD_CHANNEL_ID"),
            discord_bot_token=required_env("DISCORD_BOT_TOKEN"),
            message_thumbnail=optional_env("MESSAGE_THUMBNAIL"),
            check_interval_seconds=env_float(
                ("CHECK_INTERVAL_SECONDS", "CHECK_INTERVAL"),
                DEFAULT_CHECK_INTERVAL_SECONDS,
                minimum=1.0,
            ),
            announce_delay_seconds=env_float(
                ("ANNOUNCE_DELAY_SECONDS",),
                DEFAULT_ANNOUNCE_DELAY_SECONDS,
                minimum=0.0,
            ),
            request_timeout_seconds=env_float(
                ("REQUEST_TIMEOUT_SECONDS",),
                DEFAULT_REQUEST_TIMEOUT_SECONDS,
                minimum=1.0,
            ),
            solve_fetch_concurrency=env_int(
                "SOLVE_FETCH_CONCURRENCY",
                DEFAULT_SOLVE_FETCH_CONCURRENCY,
                minimum=1,
            ),
            state_db_path=Path(optional_env("FIRST_BLOOD_DB_PATH") or DEFAULT_DB_PATH),
            display_timezone=optional_env("DISPLAY_TIMEZONE")
            or DEFAULT_DISPLAY_TIMEZONE,
            ctfd_site_password=optional_env("CTFD_SITE_PASSWORD"),
        )


@dataclass(frozen=True)
class Challenge:
    id: int
    name: str


@dataclass(frozen=True)
class SolveSnapshot:
    challenge_id: int
    fingerprint: str
    solver_id: str | None
    solver_name: str
    solved_at_utc: datetime


@dataclass(frozen=True)
class Announcement:
    challenge_id: int
    challenge_name: str
    solve: SolveSnapshot

    @property
    def queue_key(self) -> tuple[int, str]:
        return (self.challenge_id, self.solve.fingerprint)


def clean_env_value(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip().strip('"').strip("'").strip()
    return value or None


def optional_env(name: str) -> str | None:
    return clean_env_value(os.getenv(name))


def required_env(name: str) -> str:
    value = optional_env(name)
    if value is None:
        raise ConfigError(f"Variable d'environnement manquante: {name}")
    return value


def env_float(names: tuple[str, ...], default: float, minimum: float) -> float:
    for name in names:
        value = optional_env(name)
        if value is None:
            continue
        try:
            parsed = float(value)
        except ValueError as exc:
            raise ConfigError(f"{name} doit etre un nombre") from exc
        if parsed < minimum:
            raise ConfigError(f"{name} doit etre >= {minimum}")
        return parsed
    return default


def env_int(name: str, default: int | None = None, minimum: int | None = None) -> int:
    value = optional_env(name)
    if value is None:
        if default is None:
            raise ConfigError(f"Variable d'environnement manquante: {name}")
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} doit etre un entier") from exc
    if minimum is not None and parsed < minimum:
        raise ConfigError(f"{name} doit etre >= {minimum}")
    return parsed


def normalize_ctfd_api_url(raw_url: str) -> str:
    url = raw_url.rstrip("/")
    if url.endswith("/api/v1/challenges"):
        return url[: -len("/challenges")]
    if url.endswith("/api/v1"):
        return url
    return f"{url}/api/v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_ctfd_datetime(value: str) -> datetime:
    if not value:
        raise ValueError("date CTFd vide")

    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"

    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def solve_identity(solve: dict[str, Any]) -> str | None:
    for key in ("account_id", "team_id", "user_id", "id", "account_url"):
        value = solve.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def solve_name(solve: dict[str, Any]) -> str:
    for key in ("name", "team_name", "user_name", "account_name"):
        value = solve.get(key)
        if value:
            return str(value)
    return "Inconnue"


def normalize_solve(challenge_id: int, solve: dict[str, Any]) -> SolveSnapshot:
    solved_at = parse_ctfd_datetime(str(solve.get("date", "")))
    solver_id = solve_identity(solve)
    identity_part = solver_id or "unknown"
    fingerprint = (
        f"challenge={challenge_id}|date={solved_at.isoformat()}|solver={identity_part}"
    )
    return SolveSnapshot(
        challenge_id=challenge_id,
        fingerprint=fingerprint,
        solver_id=solver_id,
        solver_name=solve_name(solve),
        solved_at_utc=solved_at,
    )


def first_solve_snapshot(
    challenge_id: int, solves: list[dict[str, Any]]
) -> SolveSnapshot | None:
    snapshots: list[SolveSnapshot] = []
    for solve in solves:
        try:
            snapshots.append(normalize_solve(challenge_id, solve))
        except (TypeError, ValueError) as exc:
            LOGGER.warning(
                "Solve ignore pour le challenge %s: date invalide (%s)",
                challenge_id,
                exc,
            )

    if not snapshots:
        return None
    return min(snapshots, key=lambda item: (item.solved_at_utc, item.fingerprint))


def format_solved_at(dt: datetime, timezone_name: str) -> str:
    try:
        display_tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        LOGGER.warning("Timezone inconnue %s, fallback UTC", timezone_name)
        display_tz = timezone.utc
    return dt.astimezone(display_tz).strftime("%d/%m/%Y %H:%M:%S %Z")


class FirstBloodStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        if self.db_path.parent != Path("."):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.ensure_schema()

    def ensure_schema(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS first_bloods (
                challenge_id INTEGER PRIMARY KEY,
                challenge_name TEXT NOT NULL,
                solve_fingerprint TEXT,
                solver_id TEXT,
                solver_name TEXT,
                solved_at TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                legacy_csv INTEGER NOT NULL DEFAULT 0,
                current_has_solves INTEGER NOT NULL DEFAULT 1,
                discord_message_id INTEGER,
                announced_at TEXT,
                last_seen_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                send_attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT
            )
            """
        )
        self.connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_first_bloods_status
            ON first_bloods(status)
            """
        )
        self.connection.commit()

    def migrate_legacy_csv(self, csv_path: Path) -> int:
        if not csv_path.is_file():
            return 0

        migrated = 0
        now = utc_now_iso()
        with csv_path.open(mode="r", encoding="utf-8", newline="") as csv_file:
            reader = csv.reader(csv_file)
            for row in reader:
                if not row:
                    continue
                challenge_id_text = row[0].strip()
                if not challenge_id_text.isdigit():
                    continue
                challenge_id = int(challenge_id_text)
                cursor = self.connection.execute(
                    """
                    INSERT OR IGNORE INTO first_bloods (
                        challenge_id,
                        challenge_name,
                        solve_fingerprint,
                        status,
                        legacy_csv,
                        current_has_solves,
                        last_seen_at,
                        updated_at
                    )
                    VALUES (?, '', NULL, 'announced', 1, 0, ?, ?)
                    """,
                    (challenge_id, now, now),
                )
                migrated += cursor.rowcount
        self.connection.commit()
        return migrated

    def close(self) -> None:
        self.connection.close()

    def get(self, challenge_id: int) -> sqlite3.Row | None:
        return self.connection.execute(
            "SELECT * FROM first_bloods WHERE challenge_id = ?",
            (challenge_id,),
        ).fetchone()

    def observe_first_solve(self, challenge: Challenge, solve: SolveSnapshot) -> bool:
        row = self.get(challenge.id)
        now = utc_now_iso()

        if row is not None and row["legacy_csv"]:
            self.connection.execute(
                """
                UPDATE first_bloods
                SET challenge_name = ?,
                    solve_fingerprint = ?,
                    solver_id = ?,
                    solver_name = ?,
                    solved_at = ?,
                    status = 'announced',
                    legacy_csv = 0,
                    current_has_solves = 1,
                    last_seen_at = ?,
                    updated_at = ?,
                    last_error = NULL
                WHERE challenge_id = ?
                """,
                (
                    challenge.name,
                    solve.fingerprint,
                    solve.solver_id,
                    solve.solver_name,
                    solve.solved_at_utc.isoformat(),
                    now,
                    now,
                    challenge.id,
                ),
            )
            self.connection.commit()
            return False

        if row is None:
            self.connection.execute(
                """
                INSERT INTO first_bloods (
                    challenge_id,
                    challenge_name,
                    solve_fingerprint,
                    solver_id,
                    solver_name,
                    solved_at,
                    status,
                    current_has_solves,
                    last_seen_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'pending', 1, ?, ?)
                """,
                (
                    challenge.id,
                    challenge.name,
                    solve.fingerprint,
                    solve.solver_id,
                    solve.solver_name,
                    solve.solved_at_utc.isoformat(),
                    now,
                    now,
                ),
            )
            self.connection.commit()
            return True

        if row["solve_fingerprint"] == solve.fingerprint:
            self.connection.execute(
                """
                UPDATE first_bloods
                SET challenge_name = ?,
                    solver_id = ?,
                    solver_name = ?,
                    solved_at = ?,
                    current_has_solves = 1,
                    last_seen_at = ?,
                    updated_at = ?
                WHERE challenge_id = ?
                """,
                (
                    challenge.name,
                    solve.solver_id,
                    solve.solver_name,
                    solve.solved_at_utc.isoformat(),
                    now,
                    now,
                    challenge.id,
                ),
            )
            self.connection.commit()
            return row["status"] in {"pending", "failed"}

        self.connection.execute(
            """
            UPDATE first_bloods
            SET challenge_name = ?,
                solve_fingerprint = ?,
                solver_id = ?,
                solver_name = ?,
                solved_at = ?,
                status = 'pending',
                legacy_csv = 0,
                current_has_solves = 1,
                discord_message_id = NULL,
                announced_at = NULL,
                last_seen_at = ?,
                updated_at = ?,
                send_attempts = 0,
                last_error = NULL
            WHERE challenge_id = ?
            """,
            (
                challenge.name,
                solve.fingerprint,
                solve.solver_id,
                solve.solver_name,
                solve.solved_at_utc.isoformat(),
                now,
                now,
                challenge.id,
            ),
        )
        self.connection.commit()
        return True

    def mark_no_solves(self, challenge: Challenge) -> None:
        if self.get(challenge.id) is None:
            return

        now = utc_now_iso()
        self.connection.execute(
            """
            UPDATE first_bloods
            SET challenge_name = ?,
                current_has_solves = 0,
                legacy_csv = 0,
                last_seen_at = ?,
                updated_at = ?
            WHERE challenge_id = ?
            """,
            (challenge.name, now, now, challenge.id),
        )
        self.connection.commit()

    def is_sendable(self, announcement: Announcement) -> bool:
        row = self.get(announcement.challenge_id)
        if row is None:
            return False
        return (
            row["solve_fingerprint"] == announcement.solve.fingerprint
            and row["current_has_solves"] == 1
            and row["status"] in {"pending", "failed"}
        )

    def record_send_attempt(self, announcement: Announcement) -> None:
        now = utc_now_iso()
        self.connection.execute(
            """
            UPDATE first_bloods
            SET send_attempts = send_attempts + 1,
                status = 'pending',
                updated_at = ?
            WHERE challenge_id = ?
              AND solve_fingerprint = ?
            """,
            (now, announcement.challenge_id, announcement.solve.fingerprint),
        )
        self.connection.commit()

    def mark_announced(self, announcement: Announcement, message_id: int) -> None:
        now = utc_now_iso()
        self.connection.execute(
            """
            UPDATE first_bloods
            SET status = 'announced',
                discord_message_id = ?,
                announced_at = ?,
                updated_at = ?,
                last_error = NULL
            WHERE challenge_id = ?
              AND solve_fingerprint = ?
            """,
            (
                message_id,
                now,
                now,
                announcement.challenge_id,
                announcement.solve.fingerprint,
            ),
        )
        self.connection.commit()

    def mark_failed(self, announcement: Announcement, error: str) -> None:
        now = utc_now_iso()
        self.connection.execute(
            """
            UPDATE first_bloods
            SET status = 'failed',
                last_error = ?,
                updated_at = ?
            WHERE challenge_id = ?
              AND solve_fingerprint = ?
            """,
            (
                error[:1000],
                now,
                announcement.challenge_id,
                announcement.solve.fingerprint,
            ),
        )
        self.connection.commit()


class CTFdClient:
    def __init__(self, session: aiohttp.ClientSession, config: BotConfig):
        self.session = session
        self.config = config

    async def fetch_challenges(self) -> list[Challenge] | None:
        payload = await self.get_json("/challenges")
        if payload is None:
            return None

        data = payload.get("data")
        if not isinstance(data, list):
            LOGGER.warning("Reponse CTFd challenges inattendue: data n'est pas une liste")
            return None

        challenges: list[Challenge] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                challenge_id = int(item["id"])
            except (KeyError, TypeError, ValueError):
                LOGGER.warning("Challenge ignore: id invalide dans %s", item)
                continue
            name = str(item.get("name") or f"Challenge #{challenge_id}")
            challenges.append(Challenge(id=challenge_id, name=name))
        return challenges

    async def fetch_solves(self, challenge_id: int) -> list[dict[str, Any]] | None:
        payload = await self.get_json(f"/challenges/{challenge_id}/solves")
        if payload is None:
            return None

        data = payload.get("data")
        if not isinstance(data, list):
            LOGGER.warning(
                "Reponse CTFd solves inattendue pour challenge %s: data n'est pas une liste",
                challenge_id,
            )
            return None
        return [item for item in data if isinstance(item, dict)]

    async def get_json(self, path: str) -> dict[str, Any] | None:
        url = f"{self.config.ctfd_api_base_url}{path}"
        cookies = None
        if self.config.ctfd_site_password:
            cookies = {"site_password": self.config.ctfd_site_password}

        try:
            async with self.session.get(
                url,
                headers=self.config.request_headers,
                cookies=cookies,
            ) as response:
                if response.status != 200:
                    body = await response.text()
                    LOGGER.warning(
                        "CTFd indisponible ou refuse la requete %s (%s): %s",
                        url,
                        response.status,
                        body[:300],
                    )
                    return None

                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            LOGGER.warning("Erreur reseau CTFd sur %s: %s", url, exc)
            return None

        if not isinstance(payload, dict):
            LOGGER.warning("Reponse CTFd invalide sur %s: JSON non objet", url)
            return None
        if payload.get("success") is False:
            LOGGER.warning("CTFd retourne success=false sur %s: %s", url, payload)
            return None
        return payload


class FirstBloodBot(commands.Bot):
    def __init__(self, config: BotConfig):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.config = config
        self.session: aiohttp.ClientSession | None = None
        self.ctfd: CTFdClient | None = None
        self.store: FirstBloodStore | None = None
        self.announcement_queue: asyncio.Queue[Announcement] = asyncio.Queue()
        self.queued_announcements: set[tuple[int, str]] = set()
        self.announcer_task: asyncio.Task[None] | None = None

    async def setup_hook(self) -> None:
        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout_seconds)
        self.session = aiohttp.ClientSession(timeout=timeout)
        self.ctfd = CTFdClient(self.session, self.config)
        self.store = FirstBloodStore(self.config.state_db_path)

        migrated = self.store.migrate_legacy_csv(Path(LEGACY_FIRST_BLOOD_FILE))
        if migrated:
            LOGGER.info(
                "%s entree(s) migree(s) depuis %s vers %s",
                migrated,
                LEGACY_FIRST_BLOOD_FILE,
                self.config.state_db_path,
            )

        self.announcer_task = asyncio.create_task(self.announcement_worker())
        self.check_first_blood.change_interval(
            seconds=self.config.check_interval_seconds
        )
        self.check_first_blood.start()

    async def close(self) -> None:
        self.check_first_blood.cancel()

        if self.announcer_task:
            self.announcer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.announcer_task

        if self.session and not self.session.closed:
            await self.session.close()

        if self.store:
            self.store.close()

        await super().close()

    async def on_ready(self) -> None:
        LOGGER.info("Connecte a Discord en tant que %s", self.user)

    @tasks.loop(seconds=DEFAULT_CHECK_INTERVAL_SECONDS)
    async def check_first_blood(self) -> None:
        if self.ctfd is None or self.store is None:
            return

        challenges = await self.ctfd.fetch_challenges()
        if challenges is None:
            LOGGER.info(
                "CTFd down/pausé/inaccessible, prochain essai dans %.1fs",
                self.config.check_interval_seconds,
            )
            return

        if not challenges:
            LOGGER.info("Aucun challenge visible pour le moment")
            return

        semaphore = asyncio.Semaphore(self.config.solve_fetch_concurrency)

        async def process_challenge(challenge: Challenge) -> None:
            async with semaphore:
                await self.process_challenge(challenge)

        results = await asyncio.gather(
            *(process_challenge(challenge) for challenge in challenges),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                LOGGER.error(
                    "Erreur pendant le check first blood",
                    exc_info=(type(result), result, result.__traceback__),
                )

    @check_first_blood.before_loop
    async def before_check_first_blood(self) -> None:
        await self.wait_until_ready()

    @check_first_blood.error
    async def check_first_blood_error(self, error: Exception) -> None:
        LOGGER.error(
            "Loop first blood en erreur",
            exc_info=(type(error), error, error.__traceback__),
        )

    async def process_challenge(self, challenge: Challenge) -> None:
        if self.ctfd is None or self.store is None:
            return

        solves = await self.ctfd.fetch_solves(challenge.id)
        if solves is None:
            return

        first_solve = first_solve_snapshot(challenge.id, solves)
        if first_solve is None:
            self.store.mark_no_solves(challenge)
            return

        should_announce = self.store.observe_first_solve(challenge, first_solve)
        if should_announce:
            await self.enqueue_announcement(
                Announcement(
                    challenge_id=challenge.id,
                    challenge_name=challenge.name,
                    solve=first_solve,
                )
            )

    async def enqueue_announcement(self, announcement: Announcement) -> None:
        if announcement.queue_key in self.queued_announcements:
            return

        self.queued_announcements.add(announcement.queue_key)
        await self.announcement_queue.put(announcement)
        LOGGER.info(
            "Annonce first blood en file: challenge=%s solver=%s solved_at=%s",
            announcement.challenge_name,
            announcement.solve.solver_name,
            announcement.solve.solved_at_utc.isoformat(),
        )

    async def announcement_worker(self) -> None:
        while True:
            announcement = await self.announcement_queue.get()
            attempted_send = False
            try:
                if self.store is None or not self.store.is_sendable(announcement):
                    continue
                if not await self.revalidate_announcement(announcement):
                    continue

                attempted_send = True
                self.store.record_send_attempt(announcement)
                channel = await self.resolve_announcement_channel()
                embed = self.build_announcement_embed(announcement)
                message = await channel.send(embed=embed)
                self.store.mark_announced(announcement, message.id)
                LOGGER.info(
                    "First blood annonce: challenge=%s solver=%s message_id=%s",
                    announcement.challenge_name,
                    announcement.solve.solver_name,
                    message.id,
                )
            except Exception as exc:
                if self.store is not None:
                    self.store.mark_failed(announcement, str(exc))
                LOGGER.exception(
                    "Impossible d'annoncer le first blood du challenge %s",
                    announcement.challenge_id,
                )
            finally:
                self.queued_announcements.discard(announcement.queue_key)
                self.announcement_queue.task_done()
                if attempted_send and self.config.announce_delay_seconds:
                    await asyncio.sleep(self.config.announce_delay_seconds)

    async def revalidate_announcement(self, announcement: Announcement) -> bool:
        if self.ctfd is None or self.store is None:
            return False

        solves = await self.ctfd.fetch_solves(announcement.challenge_id)
        if solves is None:
            raise RuntimeError("Validation CTFd impossible avant annonce Discord")

        challenge = Challenge(announcement.challenge_id, announcement.challenge_name)
        current_first_solve = first_solve_snapshot(announcement.challenge_id, solves)
        if current_first_solve is None:
            self.store.mark_no_solves(challenge)
            return False

        if current_first_solve.fingerprint != announcement.solve.fingerprint:
            should_announce = self.store.observe_first_solve(
                challenge,
                current_first_solve,
            )
            if should_announce:
                await self.enqueue_announcement(
                    Announcement(
                        challenge_id=announcement.challenge_id,
                        challenge_name=announcement.challenge_name,
                        solve=current_first_solve,
                    )
                )
            return False

        self.store.observe_first_solve(challenge, current_first_solve)
        return self.store.is_sendable(announcement)

    async def resolve_announcement_channel(self) -> Any:
        channel = self.get_channel(self.config.discord_channel_id)
        if channel is None:
            channel = await self.fetch_channel(self.config.discord_channel_id)
        if not hasattr(channel, "send"):
            raise RuntimeError(
                f"Le channel Discord {self.config.discord_channel_id} ne permet pas send()"
            )
        return channel

    def build_announcement_embed(self, announcement: Announcement) -> discord.Embed:
        solved_at = format_solved_at(
            announcement.solve.solved_at_utc,
            self.config.display_timezone,
        )
        embed = discord.Embed(
            title="First Blood!",
            description=(
                f"**Challenge :** `{announcement.challenge_name}`\n"
                f"**Equipe :** {announcement.solve.solver_name}\n"
                f"**Resolu :** {solved_at}"
            ),
            color=0xFF0000,
            timestamp=announcement.solve.solved_at_utc,
        )
        embed.set_footer(text=f"Challenge ID: {announcement.challenge_id}")
        if self.config.message_thumbnail:
            embed.set_thumbnail(url=self.config.message_thumbnail)
        return embed


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def main() -> None:
    configure_logging()
    try:
        config = BotConfig.from_env()
    except ConfigError as exc:
        LOGGER.error("Configuration invalide: %s", exc)
        raise SystemExit(1) from exc

    bot = FirstBloodBot(config)
    bot.run(config.discord_bot_token)


if __name__ == "__main__":
    main()
