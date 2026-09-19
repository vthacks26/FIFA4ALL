"""Adaptive gesture rebinding during orientation.

A drill asks the player to perform one movement. If they reliably perform a
different one instead, the binding follows what they actually did. Repeating
the movement is what confirms it; there is no separate confirm step, because
confirming would need an input the player may not have bound yet.

The hard problem here is not detecting a repetition, it is deciding WHICH
movement was repeated. Face measurements are not independent: a jaw drop
changes apparent face geometry, and everything normalized by face width moves
with it. Picking the channel with the largest raw swing would therefore rebind
to side effects rather than intent. A challenger only wins on specificity --
it must dominate by a margin while the asked-for channel stays near rest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import fmean, pstdev
from typing import Literal, Mapping

from tracking.bindings import CHANNELS, GestureChannel

# A challenger must exceed the asked-for channel by this factor before it is
# treated as intent. 1.0 would rebind on measurement noise; the margin is what
# separates "they did something else" from "the asked channel moved a bit less
# this rep".
SPECIFICITY_MARGIN = 1.8

# While a challenger wins, the asked-for channel must stay under this many
# standard deviations from rest. Above it, both moved together, which means the
# two are correlated and neither can be called intent.
ASKED_QUIET_Z = 2.5

# A swing smaller than this is indistinguishable from resting noise.
MIN_PULSE_Z = 3.0

# Deliberate movements are held. Anything briefer is a twitch or a tracking
# glitch, and this is also the first line of defence against involuntary
# movement, which is fast.
MIN_HOLD_SECONDS = 0.12

Outcome = Literal["none", "weak", "progress", "switched", "confirmed"]


@dataclass(frozen=True)
class Baseline:
    """Per-feature resting statistics measured for this player.

    Thresholds expressed in standard deviations from THIS player's rest are the
    only ones that transfer across faces, lighting and cameras. A constant
    cannot: a resting mouth reads 0.064 on one tester and near zero on another.
    """

    means: Mapping[str, float]
    sigmas: Mapping[str, float]

    @classmethod
    def from_samples(cls, samples: Mapping[str, list[float]]) -> "Baseline":
        """Build from rest-period samples, one list per feature."""

        if not samples:
            raise ValueError("baseline needs at least one sampled feature")
        means: dict[str, float] = {}
        sigmas: dict[str, float] = {}
        for feature, values in samples.items():
            if len(values) < 2:
                raise ValueError(f"{feature}: need at least 2 rest samples, got {len(values)}")
            means[feature] = fmean(values)
            # A perfectly still signal would give sigma 0 and an infinite
            # z-score, so hold a floor well below any real gesture swing.
            sigmas[feature] = max(pstdev(values), 1e-4)
        return cls(means=means, sigmas=sigmas)

    def z(self, feature: str, value: float | None) -> float:
        """Signed distance from rest in standard deviations. 0.0 if unknown."""

        if value is None or feature not in self.means:
            return 0.0
        return (value - self.means[feature]) / self.sigmas[feature]


@dataclass(frozen=True)
class Pulse:
    """One completed repetition of a movement."""

    channel: str
    peak_z: float
    duration_seconds: float
    # z of every channel at this pulse's peak, used to judge specificity.
    context: Mapping[str, float]


@dataclass
class _PulseDetector:
    """Detect one complete rep: rise, hold, release.

    Requiring the release before counting is deliberate. Counting on the rise
    would let a single long hold register as many reps.
    """

    channel: GestureChannel
    on_z: float = MIN_PULSE_Z
    off_z: float = MIN_PULSE_Z * 0.6
    min_hold: float = MIN_HOLD_SECONDS
    _active: bool = False
    _since: float | None = None
    _peak: float = 0.0
    _context: dict[str, float] = field(default_factory=dict)

    def update(self, z: float, now: float, context: Mapping[str, float]) -> Pulse | None:
        if not self._active:
            if z >= self.on_z:
                self._active = True
                self._since = now
                self._peak = z
                self._context = dict(context)
            return None

        if z > self._peak:
            self._peak = z
            self._context = dict(context)

        if z <= self.off_z:
            started = self._since
            self._active = False
            self._since = None
            held = 0.0 if started is None else now - started
            if held < self.min_hold:
                # Too brief to be deliberate. Discard rather than count.
                return None
            return Pulse(
                channel=self.channel.name,
                peak_z=self._peak,
                duration_seconds=held,
                context=dict(self._context),
            )
        return None

    def reset(self) -> None:
        self._active = False
        self._since = None
        self._peak = 0.0
        self._context = {}


@dataclass(frozen=True)
class RebindState:
    """What the drill should show after one frame."""

    outcome: Outcome
    candidate: str | None
    reps: int
    required: int
    # Set when `outcome` is "switched", so the UI can say plainly what changed.
    switched_from: str | None = None

    @property
    def finished(self) -> bool:
        return self.outcome == "confirmed"


def dominant_channel(pulse: Pulse, asked: str) -> str | None:
    """Which channel a pulse should be credited to, or None if ambiguous.

    Returns `asked` whenever the asked-for channel is a credible explanation,
    because the player was told to do that and deserves the benefit of the
    doubt. A challenger has to clear both the margin and the quiet test.
    """

    asked_z = abs(pulse.context.get(asked, 0.0))
    best = pulse.channel
    best_z = abs(pulse.context.get(best, pulse.peak_z))

    if best == asked:
        return asked
    if asked_z >= best_z / SPECIFICITY_MARGIN:
        # The asked channel moved comparably. Cannot distinguish intent from
        # a correlated side effect, so credit what was asked for.
        return asked
    if asked_z > ASKED_QUIET_Z:
        # Both channels moved a long way from rest together. They are
        # correlated; rebinding here would chase a side effect.
        return None
    if best_z < MIN_PULSE_Z:
        return None
    return best


@dataclass
class RebindEngine:
    """Run one drill: watch every channel, decide what the player is doing."""

    asked: str
    baseline: Baseline
    required_reps: int = 3
    candidates: tuple[str, ...] = ()
    _detectors: dict[str, _PulseDetector] = field(default_factory=dict, init=False)
    _candidate: str | None = field(default=None, init=False)
    _reps: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.asked not in CHANNELS:
            raise ValueError(f"unknown asked channel: {self.asked}")
        if self.required_reps < 1:
            raise ValueError("required_reps must be at least 1")
        names = self.candidates or tuple(
            name for name, channel in CHANNELS.items() if channel.selectable
        )
        if self.asked not in names:
            names = (self.asked, *names)
        self._detectors = {name: _PulseDetector(CHANNELS[name]) for name in names}
        self._candidate = self.asked

    def update(self, features: Mapping[str, float | None], now: float) -> RebindState:
        """Feed one frame of features and return the drill state."""

        context = {
            name: abs(self.baseline.z(detector.channel.feature, features.get(detector.channel.feature)))
            if detector.channel.use_magnitude
            else self.baseline.z(detector.channel.feature, features.get(detector.channel.feature))
            for name, detector in self._detectors.items()
        }

        pulses: list[Pulse] = []
        for name, detector in self._detectors.items():
            if not self._available(detector.channel, features):
                # A missing landmark must not read as a resting value.
                detector.reset()
                continue
            # `context` already takes the magnitude for channels that fire in
            # either direction. Passing the signed value for the rest matters:
            # abs() here would make a mouth held tighter shut than rest read as
            # a mouth-open gesture.
            pulse = detector.update(context[name], now, context)
            if pulse is not None:
                pulses.append(pulse)

        if not pulses:
            return self._state("none")

        # Several channels can complete a pulse on the same frame when they are
        # correlated. Judge the largest, which is the one most likely to be the
        # movement, then let specificity decide whether it earns the credit.
        pulse = max(pulses, key=lambda p: abs(p.context.get(p.channel, p.peak_z)))
        credited = dominant_channel(pulse, self.asked)
        if credited is None:
            return self._state("none")

        if credited != self._candidate:
            previous = self._candidate
            self._candidate = credited
            # A switch starts the count over. The new movement earns its own
            # repetitions rather than inheriting the old one's progress.
            self._reps = 1
            return self._state("switched", switched_from=previous)

        self._reps += 1
        if self._reps >= self.required_reps:
            return self._state("confirmed")
        return self._state("progress")

    def _available(self, channel: GestureChannel, features: Mapping[str, float | None]) -> bool:
        return all(features.get(name) is not None for name in channel.required_features)

    def _state(self, outcome: Outcome, *, switched_from: str | None = None) -> RebindState:
        return RebindState(
            outcome=outcome,
            candidate=self._candidate,
            reps=self._reps,
            required=self.required_reps,
            switched_from=switched_from,
        )
