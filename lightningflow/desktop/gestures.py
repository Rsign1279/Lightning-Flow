"""Clock-driven shortcut gestures. No hooks, sleeps, audio or GUI dependencies."""
from dataclasses import dataclass


@dataclass
class HoldToTalkGesture:
    """A tap has no side effects. A confirmed hold ends directly on release."""
    hold_seconds: float = .12
    state: str = 'idle'
    down: bool = False
    deadline: float = 0.

    def press(self,now):
        if self.down or self.state!='idle': return ()
        self.down=True
        self.state='armed'
        self.deadline=now+self.hold_seconds
        return ()

    def tick(self,now):
        if self.state=='armed' and self.down and now>=self.deadline:
            self.state='held'
            return ('start',)
        return ()

    def release(self,now):
        if not self.down: return ()
        self.down=False
        if self.state=='armed':
            self.reset()
            return ()
        if self.state=='held':
            self.state='finishing'
            return ('stop',)
        return ()

    def reset(self):
        self.state='idle'
        self.down=False
        self.deadline=0.


@dataclass
class RecordingGesture:
    double_seconds: float = .32
    tap_seconds: float = .20
    state: str = 'idle'
    down: bool = False
    pressed_at: float = 0.
    deadline: float = 0.

    def press(self, now):
        if self.down:
            return ()  # Windows key auto-repeat is never a second press.
        self.down = True
        if self.state == 'waiting':
            if now <= self.deadline:
                self.state = 'locked'
                return ('resume', 'locked')
            self.state = 'finishing'
            return ('stop',)
        if self.state == 'locked':
            self.state = 'finishing'
            return ('stop',)
        if self.state == 'idle':
            self.state = 'held'
            self.pressed_at = now
            return ('start',)
        return ()

    def release(self, now):
        if not self.down:
            return ()
        self.down = False
        if self.state != 'held':
            return ()
        if now-self.pressed_at <= self.tap_seconds:
            self.state = 'waiting'
            self.deadline = now+self.double_seconds
            return ('pause',)
        self.state = 'finishing'
        return ('stop',)

    def tick(self, now):
        if self.state == 'waiting' and now >= self.deadline:
            self.state = 'finishing'
            return ('stop',)
        return ()

    def reset(self):
        self.state = 'idle'
        self.down = False
        self.deadline = 0.
