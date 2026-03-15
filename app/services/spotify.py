import aiohttp
import urllib.parse

class SpotifyError(Exception):
    pass

async def get_spotify_track_info(url: str) -> str:
    """
    Fetches the track name and artist from Spotify using their public OEmbed API.
    Returns a search string like "Artist - Track Name"
    """
    oembed_url = f"https://open.spotify.com/oembed?url={urllib.parse.quote(url)}"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(oembed_url) as response:
            if response.status != 200:
                raise SpotifyError("Не удалось получить данные о треке из Spotify. Проверьте ссылку.")
            
            data = await response.json()
            title = data.get("title")
            # For Spotify oembed, the title often contains "Track Name"
            # But sometimes "provider_name" is just Spotify. The title is usually enough.
            # E.g. title: "Blinding Lights - The Weeknd"
            if not title:
                raise SpotifyError("Не удалось извлечь название трека.")
                
            return title
