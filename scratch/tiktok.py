from TikTokApi import TikTokApi
from datetime import datetime, timezone
import asyncio
import jso
import os
from typing import Any, Dict, List, Optional


class TikTokBigScraper:
    def __init__(
        self,
        num_sessions: int = 3,
        headless: bool = True,
        sleep_after_session_create: int = 5,
        pause_every: int = 50,
        pause_seconds: float = 2.0,
        max_retries: int = 3,
        retry_backoff: float = 2.0,
    ):
        self.api: Optional[TikTokApi] = None
        self.num_sessions = num_sessions
        self.headless = headless
        self.sleep_after_session_create = sleep_after_session_create

        self.pause_every = pause_every
        self.pause_seconds = pause_seconds

        self.max_retries = max_retries
        self.retry_backoff = retry_backoff

    async def initialize(self) -> bool:
        """Khởi tạo TikTokApi + session browser (Playwright)."""
        try:
            self.api = TikTokApi()
            await self.api.create_sessions(
                num_sessions=self.num_sessions,
                sleep_after=self.sleep_after_session_create,
                headless=self.headless,
            )
            print(f"✓ Đã khởi tạo TikTokApi thành công! (sessions={self.num_sessions}, headless={self.headless})")
            return True
        except Exception as e:
            error_msg = str(e)
            print(f"✗ Lỗi khi khởi tạo API: {error_msg}")

            if "Executable doesn't exist" in error_msg or "playwright install" in error_msg:
                print("\n⚠️  Browser chưa được cài đặt cho Playwright!")
                print("   Chạy các lệnh sau trong terminal:")
                print("   → pip install playwright")
                print("   → python -m playwright install chromium")
            return False

    async def close(self):
        """Đóng session browser."""
        try:
            if self.api:
                await self.api.close_sessions()
                await asyncio.sleep(0.3)
        except Exception:
            pass

    @staticmethod
    def parse_video(video) -> Optional[Dict[str, Any]]:
        """Ép video về dict gọn gàng."""
        try:
            v = video.as_dict
            stats = v.get("stats", {}) or {}
            author = v.get("author", {}) or {}
            music = v.get("music", {}) or {}

            create_ts = v.get("createTime", 0) or 0
            create_dt = datetime.fromtimestamp(create_ts, tz=timezone.utc)

            return {
                "video_id": v.get("id", ""),
                "description": v.get("desc", ""),
                "author": author.get("uniqueId", ""),
                "author_nickname": author.get("nickname", ""),
                "author_verified": author.get("verified", False),
                "music": music.get("title", ""),
                "music_author": music.get("authorName", ""),
                "likes": int(stats.get("diggCount", 0) or 0),
                "comments": int(stats.get("commentCount", 0) or 0),
                "shares": int(stats.get("shareCount", 0) or 0),
                "views": int(stats.get("playCount", 0) or 0),
                "duration": int((v.get("video", {}) or {}).get("duration", 0) or 0),
                "hashtags": [tag.get("title", "") for tag in (v.get("challenges", []) or []) if isinstance(tag, dict)],
                "create_time_utc": create_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "create_ts": int(create_ts),
                "video_url": f"https://www.tiktok.com/@{author.get('uniqueId', '')}/video/{v.get('id', '')}",
            }
        except Exception as e:
            print(f"Lỗi parse video: {e}")
            return None

    async def _collect(
        self,
        async_video_iter,
        target_count: int,
        autosave_path: Optional[str] = None,
        autosave_every: int = 100,
        resume: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Thu thập video từ 1 async iterator (trending/search/hashtag/user)
        cho đến khi đạt target_count hoặc hết dữ liệu.

        - autosave_path: nếu có, sẽ tự động lưu JSON theo từng lô
        - autosave_every: lưu mỗi N video
        - resume: nếu autosave file tồn tại, sẽ load và tiếp tục (lọc trùng video_id)
        """
        results: List[Dict[str, Any]] = []
        seen_ids = set()

        # Resume nếu có file autosave
        if autosave_path and resume and os.path.exists(autosave_path):
            try:
                with open(autosave_path, "r", encoding="utf-8") as f:
                    old = json.load(f)
                if isinstance(old, list):
                    for item in old:
                        if isinstance(item, dict) and item.get("video_id"):
                            vid = item["video_id"]
                            seen_ids.add(vid)
                            results.append(item)
                    print(f"↩️  Resume: đã có sẵn {len(results)} video trong {autosave_path}")
            except Exception as e:
                print(f"⚠️  Không đọc được autosave để resume: {e}")

        # Nếu đã đủ từ trước
        if len(results) >= target_count:
            return results[:target_count]

        # Collector loop + retry
        collected_since_pause = 0
        idx_start = len(results)

        for attempt in range(1, self.max_retries + 1):
            try:
                async for video in async_video_iter:
                    info = self.parse_video(video)
                    if not info:
                        continue

                    vid = info.get("video_id")
                    if not vid or vid in seen_ids:
                        continue

                    seen_ids.add(vid)
                    results.append(info)

                    i = len(results)
                    desc = (info.get("description") or "")[:60].replace("\n", " ")
                    print(f"[{i}] {desc}...")

                    # pause nhẹ để tránh rate limit
                    collected_since_pause += 1
                    if self.pause_every > 0 and collected_since_pause >= self.pause_every:
                        collected_since_pause = 0
                        await asyncio.sleep(self.pause_seconds)

                    # autosave
                    if autosave_path and autosave_every > 0 and (i % autosave_every == 0):
                        save_json(results, autosave_path, quiet=True)
                        print(f"💾 Autosave: {i} video → {autosave_path}")

                    if i >= target_count:
                        break

                # hết iterator hoặc đủ target
                break

            except Exception as e:
                print(f"⚠️  Lỗi trong quá trình collect (attempt {attempt}/{self.max_retries}): {e}")
                if attempt < self.max_retries:
                    wait_s = self.retry_backoff ** attempt
                    print(f"🔁 Retry sau {wait_s:.1f}s ...")
                    await asyncio.sleep(wait_s)
                else:
                    print("❌ Hết số lần retry. Trả về những gì đã thu thập được.")

        if len(results) > idx_start and autosave_path:
            save_json(results, autosave_path, quiet=True)

        return results[:target_count]

    async def get_trending(self, target_count=1000, **kwargs):
        print(f"🔥 Đang lấy tối đa {target_count} video trending...")
        return await self._collect(
            self.api.trending.videos(count=target_count),
            target_count=target_count,
            **kwargs,
        )

    async def search_videos(self, keyword: str, target_count=1000, **kwargs):
        print(f"🔍 Đang tìm kiếm '{keyword}' (tối đa {target_count} video)...")
        return await self._collect(
            self.api.search.videos(keyword, count=target_count),
            target_count=target_count,
            **kwargs,
        )

    async def hashtag_videos(self, hashtag: str, target_count=1000, **kwargs):
        print(f"🏷  Đang lấy video từ hashtag #{hashtag} (tối đa {target_count})...")
        tag = self.api.hashtag(name=hashtag)
        return await self._collect(
            tag.videos(count=target_count),
            target_count=target_count,
            **kwargs,
        )

    async def user_videos(self, username: str, target_count=1000, **kwargs):
        print(f"👤 Đang lấy video từ @{username} (tối đa {target_count})...")
        user = self.api.user(username=username)
        return await self._collect(
            user.videos(count=target_count),
            target_count=target_count,
            **kwargs,
        )


def save_json(data: List[Dict[str, Any]], filename: str, quiet: bool = False):
    os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    if not quiet:
        print(f"\n💾 Đã lưu {len(data)} video vào file: {filename}")


def print_stats(videos: List[Dict[str, Any]]):
    if not videos:
        return
    total_views = sum(int(v.get("views", 0) or 0) for v in videos)
    total_likes = sum(int(v.get("likes", 0) or 0) for v in videos)
    total_comments = sum(int(v.get("comments", 0) or 0) for v in videos)
    total_shares = sum(int(v.get("shares", 0) or 0) for v in videos)

    n = len(videos)
    print("\n📊 THỐNG KÊ:")
    print(f"   • Số video: {n}")
    print(f"   • Tổng views: {total_views:,}")
    print(f"   • Tổng likes: {total_likes:,}")
    print(f"   • Tổng comments: {total_comments:,}")
    print(f"   • Tổng shares: {total_shares:,}")
    print(f"   • TB views/video: {(total_views // n):,}")
    print(f"   • TB likes/video: {(total_likes // n):,}")


async def main():
    # --- cấu hình mặc định cho 1000 video ---
    scraper = TikTokBigScraper(
        num_sessions=3,                 # tăng sessions để ổn định hơn
        headless=True,
        sleep_after_session_create=5,
        pause_every=50,                 # nghỉ nhẹ mỗi 50 video
        pause_seconds=2.0,
        max_retries=3,                  # retry nếu bị chặn/lỗi mạng
        retry_backoff=2.0,
    )

    if not await scraper.initialize():
        return

    try:
        print("=" * 70)
        print("1. Trending")
        print("2. Search theo từ khóa")
        print("3. Hashtag")
        print("4. User")
        print("=" * 70)

        choice = input("Chọn chế độ (1-4) [mặc định: 1]: ").strip() or "1"
        target_str = input("Số video tối đa [mặc định: 1000]: ").strip() or "1000"
        target_count = int(target_str)

        autosave = input("Bật autosave theo lô? (y/n) [mặc định: y]: ").strip().lower()
        if autosave != "n":
            autosave_path = input("Tên file autosave [mặc định: out/tiktok_autosave.json]: ").strip() or "out/tiktok_autosave.json"
            autosave_every = int(input("Autosave mỗi bao nhiêu video? [mặc định: 100]: ").strip() or "100")
        else:
            autosave_path = None
            autosave_every = 0

        videos: List[Dict[str, Any]] = []

        if choice == "1":
            videos = await scraper.get_trending(
                target_count=target_count,
                autosave_path=autosave_path,
                autosave_every=autosave_every,
                resume=True,
            )

        elif choice == "2":
            kw = input("Nhập từ khóa: ").strip()
            if kw:
                videos = await scraper.search_videos(
                    kw,
                    target_count=target_count,
                    autosave_path=autosave_path,
                    autosave_every=autosave_every,
                    resume=True,
                )

        elif choice == "3":
            tag = input("Nhập hashtag (không cần #): ").strip()
            if tag:
                videos = await scraper.hashtag_videos(
                    tag,
                    target_count=target_count,
                    autosave_path=autosave_path,
                    autosave_every=autosave_every,
                    resume=True,
                )

        elif choice == "4":
            username = input("Nhập username (không cần @): ").strip()
            if username:
                videos = await scraper.user_videos(
                    username,
                    target_count=target_count,
                    autosave_path=autosave_path,
                    autosave_every=autosave_every,
                    resume=True,
                )

        if not videos:
            print("\n⚠️ Không lấy được video nào.")
            return

        print_stats(videos)

        save = input("\nLưu JSON cuối cùng? (y/n) [mặc định: y]: ").strip().lower()
        if save != "n":
            default_name = f"out/tiktok_{len(videos)}_videos.json"
            filename = input(f"Tên file [mặc định: {default_name}]: ").strip() or default_name
            save_json(videos, filename)

    finally:
        print("\n🔄 Đóng session...")
        await scraper.close()
        print("✓ Xong!")


if __name__ == "__main__":
    asyncio.run(main())
