import aiohttp


class Requests:

    async def post_request(self, url: str, headers: dict, params: dict = None) -> int:
        async with aiohttp.ClientSession(headers=headers) as cs:
            async with cs.post(url, params=params) as r:
                if r.status != 204:
                    return r.status, await r.json()
                else:
                    return r.status

    async def get_request(self, url: str, headers: dict, params: dict = None):
        async with aiohttp.ClientSession(headers=headers) as cs:
            async with cs.get(url, params=params) as r:
                if r.status != 204:
                    return r.status, await r.json()
                else:
                    return r.status

    async def put_request(self, url: str, headers: dict, params: dict = None):
        async with aiohttp.ClientSession(headers=headers) as cs:
            async with cs.put(url, params=params) as r:
                if r.status != 204:
                    return r.status, await r.json()
                else:
                    return r.status


class Spotify(Requests):
    def __init__(self, bot):
        self.bot = bot

    async def get_token_from_code(self, code: str):
        data = {
            "grant_type": "refresh_token",
            "refresh_token": code,
            "client_secret": "f4294b7b837940f996b3a4dcf5230628",
            "client_id": "f567fb50e0b94b4e8224d2960a00e3ce",
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        result = await self.post_request(
            "https://accounts.spotify.com/api/token", headers=headers, params=data
        )
        if result[0] == 200:
            return result[1]["access_token"]

    async def get_access_token(self):
        access_token = await self.bot.db.fetchrow(
            "SELECT access_token FROM spotify WHERE user_id = $1", 371224177186963460
        )
        return await self.get_token_from_code(access_token[0])

    async def search(self, query: str):
        access_token = await self.get_access_token()
        result = await self.get_request(
            "https://api.spotify.com/v1/search",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"q": query, "type": ["track"], "limit": 1},
        )
        return result[1]["tracks"]["items"][0]["external_urls"]["spotify"]


class Handler(object):
    def __init__(self, api_key: str):
        self.apikey = api_key
        self.baseurl = "https://ws.audioscrobbler.com/2.0/"

    async def lastfm_user_exists(self, user: str) -> bool:
        a = await self.get_user_info(user)
        return "error" not in a

    async def do_request(self, data: dict):
        async with aiohttp.ClientSession() as cs:
            async with cs.get(self.baseurl, params=data) as r:
                return await r.json()

    async def get_track_playcount(self, user: str, track: dict) -> int:
        data = {
            "method": "track.getInfo",
            "api_key": self.apikey,
            "artist": track["artist"]["#text"],
            "track": track["name"],
            "format": "json",
            "username": user,
        }
        return (await self.do_request(data))["track"]["userplaycount"]

    async def get_album_playcount(self, user: str, track: dict) -> int:
        data = {
            "method": "album.getInfo",
            "api_key": self.apikey,
            "artist": track["artist"]["#text"],
            "album": track["album"]["#text"],
            "format": "json",
            "username": user,
        }
        return (await self.do_request(data))["album"]["userplaycount"]

    async def get_artist_playcount(self, user: str, artist: str) -> int:
        data = {
            "method": "artist.getInfo",
            "api_key": self.apikey,
            "artist": artist,
            "format": "json",
            "username": user,
        }
        return (await self.do_request(data))["artist"]["stats"]["userplaycount"]

    async def get_album(self, track: dict) -> dict:
        data = {
            "method": "album.getInfo",
            "api_key": self.apikey,
            "artist": track["artist"]["#text"],
            "album": track["album"]["#text"],
            "format": "json",
        }
        return (await self.do_request(data))["album"]

    async def get_track(self, track: dict) -> dict:
        data = {
            "method": "album.getInfo",
            "api_key": self.apikey,
            "artist": track["artist"]["#text"],
            "track": track["track"]["#text"],
            "format": "json",
        }
        return await self.do_request(data)

    async def get_user_info(self, user: str) -> dict:
        data = {
            "method": "user.getinfo",
            "user": user,
            "api_key": self.apikey,
            "format": "json",
        }
        return await self.do_request(data)

    async def get_top_artists(self, user: str, count: int) -> dict:
        data = {
            "method": "user.getTopArtists",
            "user": user,
            "api_key": self.apikey,
            "format": "json",
            "limit": count,
        }
        return await self.do_request(data)

    async def get_top_tracks(self, user: str, count: int) -> dict:
        data = {
            "method": "user.getTopTracks",
            "user": user,
            "api_key": self.apikey,
            "format": "json",
            "period": "overall",
            "limit": count,
        }
        return await self.do_request(data)

    async def get_top_albums(self, user: str, count: int) -> dict:
        params = {
            "api_key": self.apikey,
            "user": user,
            "period": "overall",
            "limit": count,
            "method": "user.getTopAlbums",
            "format": "json",
        }
        return await self.do_request(params)

    async def get_tracks_recent(self, user: str, count: int = 10) -> dict:
        data = {
            "method": "user.getrecenttracks",
            "user": user,
            "api_key": self.apikey,
            "format": "json",
            "limit": count,
        }
        return await self.do_request(data)
