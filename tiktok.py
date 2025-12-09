from TikTokApi import TikTokApi
from datetime import datetime
import asyncio
import json


class TikTokBigScraper:
    def __init__(self):
        self.api = None

    async def initialize(self):
        """Khởi tạo TikTokApi + session browser"""
        try:
            self.api = TikTokApi()
            await self.api.create_sessions(
                num_sessions=1,
                sleep_after=3,
                headless=True
            )
            print("✓ Đã khởi tạo TikTokApi thành công!")
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
        """Đóng session browser"""
        try:
            if self.api:
                await self.api.close_sessions()
                await asyncio.sleep(0.3)
        except Exception:
            pass

    @staticmethod
    def parse_video(video):
        """Ép video về dict gọn gàng"""
        try:
            v = video.as_dict
            stats = v.get("stats", {})
            author = v.get("author", {})
            music = v.get("music", {})

            return {
                "video_id": v.get("id", ""),
                "description": v.get("desc", ""),
                "author": author.get("uniqueId", ""),
                "author_nickname": author.get("nickname", ""),
                "author_verified": author.get("verified", False),
                "music": music.get("title", ""),
                "music_author": music.get("authorName", ""),
                "likes": stats.get("diggCount", 0),
                "comments": stats.get("commentCount", 0),
                "shares": stats.get("shareCount", 0),
                "views": stats.get("playCount", 0),
                "duration": v.get("video", {}).get("duration", 0),
                "hashtags": [tag["title"] for tag in v.get("challenges", [])],
                "create_time": datetime.fromtimestamp(
                    v.get("createTime", 0)
                ).strftime("%Y-%m-%d %H:%M:%S"),
                "video_url": f"https://www.tiktok.com/@{author.get('uniqueId', '')}/video/{v.get('id', '')}",
            }
        except Exception as e:
            print(f"Lỗi parse video: {e}")
            return None

    async def _collect(self, async_video_iter, target_count: int):
        """
        Thu thập video từ 1 async iterator (trending/search/hashtag/user)
        cho đến khi đạt target_count hoặc hết dữ liệu.
        """
        results = []
        async for video in async_video_iter:
            info = self.parse_video(video)
            if info:
                results.append(info)
                i = len(results)
                print(f"[{i}] {info['description'][:60]}...")
            if len(results) >= target_count:
                break
        return results

    async def get_trending(self, target_count=500):
        print(f"🔥 Đang lấy tối đa {target_count} video trending...")
        return await self._collect(
            self.api.trending.videos(count=target_count),
            target_count=target_count,
        )

    async def search_videos(self, keyword: str, target_count=500):
        print(f"🔍 Đang tìm kiếm '{keyword}' (tối đa {target_count} video)...")
        return await self._collect(
            self.api.search.videos(keyword, count=target_count),
            target_count=target_count,
        )

    async def hashtag_videos(self, hashtag: str, target_count=500):
        print(f"🏷  Đang lấy video từ hashtag #{hashtag} (tối đa {target_count})...")
        tag = self.api.hashtag(name=hashtag)
        return await self._collect(
            tag.videos(count=target_count),
            target_count=target_count,
        )

    async def user_videos(self, username: str, target_count=500):
        print(f"👤 Đang lấy video từ @{username} (tối đa {target_count})...")
        user = self.api.user(username=username)
        return await self._collect(
            user.videos(count=target_count),
            target_count=target_count,
        )


def save_json(data, filename: str):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Đã lưu {len(data)} video vào file: {filename}")


def print_stats(videos):
    if not videos:
        return
    total_views = sum(v["views"] for v in videos)
    total_likes = sum(v["likes"] for v in videos)
    total_comments = sum(v["comments"] for v in videos)
    total_shares = sum(v["shares"] for v in videos)

    print("\n📊 THỐNG KÊ:")
    print(f"   • Số video: {len(videos)}")
    print(f"   • Tổng views: {total_views:,}")
    print(f"   • Tổng likes: {total_likes:,}")
    print(f"   • Tổng comments: {total_comments:,}")
    print(f"   • Tổng shares: {total_shares:,}")
    print(f"   • TB views/video: {total_views // len(videos):,}")
    print(f"   • TB likes/video: {total_likes // len(videos):,}")


async def main():
    scraper = TikTokBigScraper()
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
        target_str = input("Số video tối đa [mặc định: 500]: ").strip() or "500"
        target_count = int(target_str)

        videos = []

        if choice == "1":
            videos = await scraper.get_trending(target_count=target_count)
        elif choice == "2":
            kw = input("Nhập từ khóa: ").strip()
            if kw:
                videos = await scraper.search_videos(kw, target_count=target_count)
        elif choice == "3":
            tag = input("Nhập hashtag (không cần #): ").strip()
            if tag:
                videos = await scraper.hashtag_videos(tag, target_count=target_count)
        elif choice == "4":
            username = input("Nhập username (không cần @): ").strip()
            if username:
                videos = await scraper.user_videos(username, target_count=target_count)

        if not videos:
            print("\n⚠️ Không lấy được video nào.")
            return

        print_stats(videos)

        save = input("\nLưu JSON? (y/n) [mặc định: y]: ").strip().lower()
        if save != "n":
            default_name = "tiktok_500_videos.json"
            filename = input(f"Tên file [mặc định: {default_name}]: ").strip() or default_name
            save_json(videos, filename)

    finally:
        print("\n🔄 Đóng session...")
        await scraper.close()
        print("✓ Xong!")


if __name__ == "__main__":
    asyncio.run(main())
