class ProviderError(Exception):
    pass


class Provider:
    """A music source. play()/pause() are called when you tune in/out of the station."""
    name = "base"

    async def start(self): ...
    async def stop(self): ...
    async def play(self): ...
    async def pause(self): ...
    async def next(self): raise ProviderError("not supported by this provider")
    async def prev(self): raise ProviderError("not supported by this provider")
    async def playlists(self): raise ProviderError("not supported by this provider")
    async def select(self, uri, name=""): raise ProviderError("not supported by this provider")
    def state(self): return {}
