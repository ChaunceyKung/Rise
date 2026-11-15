"""Explicit UTC clock contract; fixed time is restricted to priced rehearsal."""
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from typing import Protocol

from actio.contracts.json import require


class Clock(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True)
class ClockSpec:
    mode: str = 'system'
    instant: str | None = None

    @classmethod
    def from_config(cls, value, execution_mode):
        require(type(value) is dict and set(value) == {'mode', 'instant'}, 'clock fields')
        mode, instant = value['mode'], value['instant']
        require(mode in ('system', 'fixed'), 'clock mode')
        if mode == 'system':
            require(instant is None, 'system clock cannot specify instant')
        else:
            require(execution_mode == 'priced_rehearsal', 'fixed clock requires priced_rehearsal')
            require(type(instant) is str and instant.endswith('Z'), 'fixed instant must be UTC Z')
            try:
                parsed = datetime.fromisoformat(instant)
            except ValueError:
                require(False, 'invalid clock instant')
            require(parsed.tzinfo == timezone.utc and parsed.isoformat().replace('+00:00', 'Z') == instant,
                    'canonical UTC clock instant required')
        return cls(mode, instant)

    def now(self):
        return datetime.now(timezone.utc) if self.mode == 'system' else datetime.fromisoformat(self.instant)

    def as_dict(self):
        return {'mode': self.mode, 'instant': self.instant}


def quote_current(c,now=None):
    spec=ClockSpec.from_config(c['clock'],c['mode'])
    require(now is None or spec.mode=='fixed' and now==spec.now(), 'clock override forbidden')
    now=spec.now()
    require(datetime.fromisoformat(c['quote']['valid_from'])<=now<datetime.fromisoformat(c['quote']['valid_until']),'quote review window expired/not yet valid')
