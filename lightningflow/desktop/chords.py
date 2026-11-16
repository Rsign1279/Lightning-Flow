"""Ordered modifier-only shortcut edges, independent of Windows/Tk/audio."""

CTRL = {0x11, 0xA2, 0xA3}
WIN = {0x5B, 0x5C}


class ControlWindowsChord:
    def __init__(self):
        self.held = set()
        self.active = False
        self.consumed_windows = set()

    def feed(self, vk, down):
        vk = 0xA2 if vk == 0x11 else vk
        was_down = vk in self.held
        suppress = vk in self.consumed_windows
        if down:
            if vk in WIN and not was_down and self.held & CTRL:
                self.consumed_windows.add(vk)
                suppress = True
            self.held.add(vk)
        else:
            self.held.discard(vk)
            self.consumed_windows.discard(vk)
        active = bool(self.held & CTRL and self.held & WIN)
        edge = None
        if active and not self.active:
            edge = 'press'
        elif self.active and not active:
            edge = 'release'
        # Never swallow the release of a Windows down we passed through: that
        # leaves Windows logically held. Win-first chords pass Ctrl and Win-up;
        # Ctrl-first chords consume both Win-down and its matching Win-up.
        self.active = active
        return edge, suppress
