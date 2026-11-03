"""Server-owned round/phase clock, independent of host tabs or WebSocket presence."""

import asyncio
import logging
import time
from datetime import timedelta

from channels.db import database_sync_to_async
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.matches.clock import COMBAT_PHASES, open_planning_window, phase_duration, timestamp
from apps.matches.models import Match, MatchEvent, MatchStatus

logger = logging.getLogger(__name__)


class MatchScheduler:
    @classmethod
    def tick(cls, now=None):
        now = now or timezone.now()
        # Retry committed outbox rows before running new simulation work.
        from apps.realtime.services import RealtimeService
        for event in MatchEvent.objects.filter(broadcasted_at__isnull=True).order_by("created_at", "sequence_number")[:200]:
            RealtimeService.broadcast_match_event(event)
        for match_id in Match.objects.filter(status=MatchStatus.ACTIVE).values_list("id", flat=True):
            try:
                cls.advance_due(match_id, now)
            except Exception:
                # Roll back this match and retry on the next tick; other rooms keep running.
                logger.exception("Match clock failed for %s", match_id)

    @classmethod
    @transaction.atomic
    def advance_due(cls, match_id, now=None):
        from apps.combat.services import CombatService
        from apps.matches.services import MatchService
        from apps.questions.services import QuestionService

        now = now or timezone.now()
        match = Match.objects.select_for_update().get(pk=match_id)
        if match.status != MatchStatus.ACTIVE:
            return

        if match.configuration.get("gameplay_mode") == "CONTINUOUS":
            cls.advance_continuous(match, now)
            return

        # Bounded catch-up after downtime. Persist each deadline, so multiple ASGI
        # workers serialize here and never award the same round twice.
        for _ in range(120):
            config = match.configuration
            timer = config.setdefault("timer_state", {})
            previous_timer = dict(timer)
            start = timestamp(timer.get("phase_started_at")) or match.started_at or now
            timer.setdefault("phase_started_at", start.isoformat())
            phase_end = start + timedelta(seconds=phase_duration(config, match.phase))
            timer.setdefault("match_deadline_at", (
                (match.started_at or now) + timedelta(seconds=config.get("match_duration_seconds", 1800))
            ).isoformat())
            if match.phase in COMBAT_PHASES and not timer.get("next_round_at"):
                open_planning_window(config, start)
            if timer != previous_timer:
                match.save(update_fields=["configuration"])
            round_end = timestamp(timer.get("next_round_at")) if match.phase in COMBAT_PHASES else None
            match_end = timestamp(timer["match_deadline_at"])

            # A round ending exactly at a phase or match deadline resolves first.
            if round_end and round_end <= min(now, phase_end, match_end):
                CombatService.execute_combat_round(
                    match, expected_round=config.get("current_round", 1), resolved_at=round_end,
                )
            elif match_end <= now and match_end <= phase_end:
                MatchService.end_match(match)
            elif phase_end <= now:
                MatchService.advance_phase(match, effective_at=phase_end)
            else:
                break
            match.refresh_from_db()
            if match.status != MatchStatus.ACTIVE:
                return

        QuestionService.expire_overdue_questions(match, now=now)
        QuestionService.expire_reward_deadlines(match, now=now)


    @classmethod
    def advance_continuous(cls, match, now):
        from apps.combat.continuous_service import ContinuousCombatService
        from apps.matches.services import MatchService
        from apps.questions.services import QuestionService

        # Bound both simulated catch-up and wall time. Large armies must yield
        # the match lock so purchases and other rooms get a turn. No ticks skip.
        # Every committed tick is replay-safe, even after process failure.
        started = time.monotonic()
        for _ in range(25):
            timer = match.configuration["timer_state"]
            phase_end = timestamp(timer["phase_ends_at"])
            tick_at = timestamp(timer.get("next_tick_at"))
            if tick_at and tick_at <= min(now, phase_end):
                ContinuousCombatService.tick(match.pk, tick_at)
            elif phase_end <= now:
                MatchService.advance_continuous_phase(match, phase_end)
            else:
                break
            match.refresh_from_db()
            if match.status != MatchStatus.ACTIVE:
                return
            if time.monotonic() - started >= 1:
                break
        QuestionService.expire_overdue_questions(match, now=now)
        QuestionService.expire_reward_deadlines(match, now=now)


class ScheduledMatchApplication:
    """Start on lifespan startup, or first request on Daphne (no lifespan support).

    The task belongs to the server event loop, not to a connection. Persisted
    deadlines survive restarts; production workers coordinate via DB row locks.
    """

    def __init__(self, application):
        self.application = application
        self.task = None

    def start(self):
        if getattr(settings, "MATCH_SCHEDULER_ENABLED", True) and (
            self.task is None or self.task.done()
        ):
            self.task = asyncio.create_task(self.run(), name="match-clock")

    async def run(self):
        while True:
            try:
                await database_sync_to_async(MatchScheduler.tick)()
            except Exception:
                logger.exception("Match clock tick failed; retrying")
            await asyncio.sleep(0.1)

    async def __call__(self, scope, receive, send):
        self.start()
        if scope["type"] != "lifespan":
            return await self.application(scope, receive, send)
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                if self.task:
                    self.task.cancel()
                    try:
                        await self.task
                    except asyncio.CancelledError:
                        pass
                await send({"type": "lifespan.shutdown.complete"})
                return
