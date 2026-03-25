"""
Twitter/X client — uses the official Twitter API v2 via tweepy.
Falls back to browser automation for actions not available on free tier.
"""

import asyncio
import random
import logging
from typing import Optional

from app.platforms.base import BasePlatformClient
from app.services.browser_session import BrowserSessionManager

logger = logging.getLogger(__name__)


class TwitterClient(BasePlatformClient):

    def __init__(self, account_id: str, credentials: dict, proxy: Optional[dict] = None):
        super().__init__(account_id, credentials, proxy)
        self.api_key = credentials.get("api_key")
        self.api_secret = credentials.get("api_secret")
        self.access_token = credentials.get("access_token")
        self.access_token_secret = credentials.get("access_token_secret")
        self.bearer_token = credentials.get("bearer_token")
        self._browser_mgr = BrowserSessionManager(account_id, proxy=proxy)
        self._client = None

    def _get_client(self):
        if not self._client:
            import tweepy
            self._client = tweepy.AsyncClient(
                bearer_token=self.bearer_token,
                consumer_key=self.api_key,
                consumer_secret=self.api_secret,
                access_token=self.access_token,
                access_token_secret=self.access_token_secret,
                wait_on_rate_limit=True,
            )
        return self._client

    async def _human_delay(self, min_s=1.0, max_s=3.0):
        await asyncio.sleep(random.uniform(min_s, max_s))

    # ── Session ──────────────────────────────────────────────────────────────

    async def authenticate(self) -> bool:
        try:
            client = self._get_client()
            me = await client.get_me()
            return me.data is not None
        except Exception as e:
            self.logger.error(f"Twitter auth failed: {e}")
            return False

    async def health_check(self) -> dict:
        valid = await self.authenticate()
        return {"valid": valid, "platform": "twitter"}

    # ── Posting ──────────────────────────────────────────────────────────────

    async def create_post(self, content: str, media_paths: list = None, metadata: dict = None) -> dict:
        client = self._get_client()
        media_ids = []
        if media_paths:
            import tweepy
            auth = tweepy.OAuth1UserHandler(
                self.api_key, self.api_secret, self.access_token, self.access_token_secret
            )
            api_v1 = tweepy.API(auth)
            for path in media_paths:
                media = api_v1.media_upload(path)
                media_ids.append(media.media_id)

        tweet = await client.create_tweet(
            text=content,
            media_ids=media_ids if media_ids else None,
        )
        tweet_id = tweet.data["id"]
        return {
            "platform_post_id": tweet_id,
            "url": f"https://twitter.com/i/web/status/{tweet_id}",
        }

    # ── Engagement ───────────────────────────────────────────────────────────

    async def like(self, target_id: str) -> bool:
        try:
            client = self._get_client()
            me = await client.get_me()
            result = await client.like(tweet_id=target_id, user_auth=True)
            return result.data.get("liked", False)
        except Exception as e:
            self.logger.error(f"Twitter like failed: {e}")
            return False

    async def unlike(self, target_id: str) -> bool:
        try:
            client = self._get_client()
            me = await client.get_me()
            result = await client.unlike(tweet_id=target_id, user_auth=True)
            return result.data.get("liked") is False
        except Exception as e:
            self.logger.error(f"Twitter unlike failed: {e}")
            return False

    async def repost(self, target_id: str) -> bool:
        try:
            client = self._get_client()
            result = await client.retweet(tweet_id=target_id, user_auth=True)
            return result.data.get("retweeted", False)
        except Exception as e:
            self.logger.error(f"Twitter repost failed: {e}")
            return False

    async def unrepost(self, target_id: str) -> bool:
        try:
            client = self._get_client()
            result = await client.unretweet(source_tweet_id=target_id, user_auth=True)
            return result.data.get("retweeted") is False
        except Exception as e:
            self.logger.error(f"Twitter unrepost failed: {e}")
            return False

    async def comment(self, target_id: str, text: str) -> dict:
        """Reply to a tweet."""
        client = self._get_client()
        reply = await client.create_tweet(
            text=text,
            in_reply_to_tweet_id=target_id,
            user_auth=True,
        )
        return {"comment_id": reply.data["id"]}

    async def follow(self, target_user_id: str) -> bool:
        try:
            client = self._get_client()
            result = await client.follow_user(target_user_id=target_user_id, user_auth=True)
            return result.data.get("following", False)
        except Exception as e:
            self.logger.error(f"Twitter follow failed: {e}")
            return False

    async def unfollow(self, target_user_id: str) -> bool:
        try:
            client = self._get_client()
            result = await client.unfollow_user(target_user_id=target_user_id, user_auth=True)
            return result.data.get("following") is False
        except Exception as e:
            self.logger.error(f"Twitter unfollow failed: {e}")
            return False

    # ── Profile / analytics ──────────────────────────────────────────────────

    async def get_profile(self) -> dict:
        client = self._get_client()
        me = await client.get_me(user_fields=["public_metrics", "description", "profile_image_url"])
        return me.data.data if me.data else {}

    async def get_analytics(self, post_id: Optional[str] = None) -> dict:
        client = self._get_client()
        if post_id:
            tweet = await client.get_tweet(
                id=post_id,
                tweet_fields=["public_metrics"],
                user_auth=True,
            )
            return tweet.data.public_metrics if tweet.data else {}
        me = await client.get_me(user_fields=["public_metrics"])
        return me.data.public_metrics if me.data else {}
