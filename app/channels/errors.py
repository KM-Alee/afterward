"""Channel failures that stay inside this slice. They do not change frozen contracts."""


class ChannelCallError(Exception):
    """A transport call did not return the shape the adapter needs."""


class WindowClosed(Exception):
    """WhatsApp free-form sends are only allowed within 24 hours of the last inbound."""


class AudioRepackageError(Exception):
    """ffmpeg could not repackage the voice note. The message does not include audio bytes."""
