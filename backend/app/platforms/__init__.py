from app.platforms.base import BasePlatformClient
from app.platforms.soundcloud.client import SoundCloudClient
from app.platforms.tiktok.client import TikTokClient
from app.platforms.twitter.client import TwitterClient
from app.platforms.spotify.client import SpotifyClient
from app.models.social_account import Platform


def get_platform_client(platform: Platform) -> type:
    mapping = {
        Platform.SOUNDCLOUD: SoundCloudClient,
        Platform.TIKTOK:     TikTokClient,
        Platform.TWITTER:    TwitterClient,
        Platform.SPOTIFY:    SpotifyClient,
    }
    return mapping[platform]
