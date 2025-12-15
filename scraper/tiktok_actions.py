from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from datetime import datetime, timezone
import json
import os
import time
import random
from typing import Any, Dict, List, Optional
from urllib.parse import quote
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TikTokSeleniumScraper:
    def __init__(
        self,
        headless: bool = True,
        sleep_min: float = 3.0,
        sleep_max: float = 5.0,
        pause_every: int = 50,
        pause_seconds: float = 2.0,
        max_retries: int = 3,
    ):
        self.driver: Optional[webdriver.Chrome] = None
        self.headless = headless
        self.sleep_min = sleep_min
        self.sleep_max = sleep_max
        self.pause_every = pause_every
        self.pause_seconds = pause_seconds
        self.max_retries = max_retries

    def initialize(self) -> bool:
        """Khởi tạo Selenium WebDriver."""
        try:
            chrome_options = Options()
            
            if self.headless:
                chrome_options.add_argument("--headless=new")
            
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option("useAutomationExtension", False)
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.set_page_load_timeout(30)
            
            logger.info(f"✓ Đã khởi tạo Selenium WebDriver thành công! (headless={self.headless})")
            return True
            
        except Exception as e:
            logger.error(f"✗ Lỗi khi khởi tạo WebDriver: {e}")
            logger.error("⚠️  Cần cài đặt ChromeDriver hoặc webdriver-manager")
            logger.error("   pip install selenium webdriver-manager")
            return False

    def close(self):
        """Đóng WebDriver."""
        try:
            if self.driver:
                self.driver.quit()
                logger.info("✓ WebDriver đã đóng")
        except Exception as e:
            logger.error(f"Lỗi khi đóng WebDriver: {e}")

    @staticmethod
    def random_sleep():
        """Sleep với thời gian random giữa sleep_min và sleep_max."""
        pass

    def random_sleep_instance(self):
        """Sleep với thời gian random giữa sleep_min và sleep_max."""
        sleep_time = random.uniform(self.sleep_min, self.sleep_max)
        time.sleep(sleep_time)
        logger.debug(f"💤 Sleep {sleep_time:.2f}s")

    def scroll_to_load_videos(self, target_count: int = 3000, max_scroll: int = 100) -> List[Dict[str, Any]]:
        """Scroll trang để load video."""
        videos = []
        seen_ids = set()
        collected = 0
        scroll_count = 0

        try:
            while collected < target_count and scroll_count < max_scroll:
                # Lấy tất cả video hiện có trên trang
                try:
                    video_elements = self.driver.find_elements(By.CSS_SELECTOR, "[data-e2e='video-card']")
                    
                    for video_elem in video_elements:
                        if collected >= target_count:
                            break

                        try:
                            # Lấy link video
                            link_elem = video_elem.find_element(By.CSS_SELECTOR, "a[href*='/video/']")
                            video_url = link_elem.get_attribute("href")
                            video_id = video_url.split("/video/")[-1].split("?")[0] if video_url else None

                            if not video_id or video_id in seen_ids:
                                continue

                            # Parse thông tin từ element
                            info = self._parse_video_element(video_elem, video_url)
                            
                            if info and info.get("video_id"):
                                seen_ids.add(video_id)
                                videos.append(info)
                                collected += 1

                                desc = (info.get("description") or "")[:60].replace("\n", " ")
                                logger.info(f"[{collected}] {desc}...")

                                # Pause nhẹ
                                if self.pause_every > 0 and (collected % self.pause_every == 0):
                                    time.sleep(self.pause_seconds)
                                    logger.info(f"⏸️  Pause {self.pause_seconds}s")

                        except Exception as e:
                            logger.debug(f"Lỗi parse video element: {e}")
                            continue

                except Exception as e:
                    logger.error(f"Lỗi lấy video elements: {e}")

                # Scroll xuống
                if collected < target_count:
                    self.driver.execute_script("window.scrollBy(0, 500);")
                    scroll_count += 1
                    self.random_sleep_instance()

            logger.info(f"✓ Đã tải {collected}/{target_count} video sau {scroll_count} lần scroll")
            return videos

        except Exception as e:
            logger.error(f"Lỗi trong quá trình scroll: {e}")
            return videos

    def _parse_video_element(self, video_elem, video_url: str) -> Optional[Dict[str, Any]]:
        """Ép video element về dict gọn gàng."""
        try:
            video_id = video_url.split("/video/")[-1].split("?")[0] if video_url else ""

            # Lấy description từ title
            try:
                desc_elem = video_elem.find_element(By.CSS_SELECTOR, "[data-e2e='video-desc']")
                description = desc_elem.text or ""
            except:
                description = ""

            # Lấy tên tác giả
            try:
                author_elem = video_elem.find_element(By.CSS_SELECTOR, "a[href*='/@']")
                author_url = author_elem.get_attribute("href")
                author = author_url.split("/@")[-1].split("?")[0] if author_url else ""
            except:
                author = ""

            # Lấy stats (likes, comments, shares, views)
            likes = self._extract_stat(video_elem, "like")
            comments = self._extract_stat(video_elem, "comment")
            shares = self._extract_stat(video_elem, "share")
            views = self._extract_stat(video_elem, "view")

            # Lấy thông tin khác từ page (nếu cần chi tiết hơn)
            hashtags = []
            music = ""
            duration = 0

            create_time_utc = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            create_ts = int(datetime.now(tz=timezone.utc).timestamp())

            return {
                "video_id": video_id,
                "description": description,
                "author": author,
                "author_nickname": author,
                "author_verified": False,
                "music": music,
                "music_author": "",
                "likes": likes,
                "comments": comments,
                "shares": shares,
                "views": views,
                "duration": duration,
                "hashtags": hashtags,
                "create_time_utc": create_time_utc,
                "create_ts": create_ts,
                "video_url": video_url,
            }

        except Exception as e:
            logger.error(f"Lỗi parse video element: {e}")
            return None

    @staticmethod
    def _extract_stat(video_elem, stat_type: str) -> int:
        """Lấy số liệu thống kê (likes, comments, etc)."""
        try:
            stat_elem = video_elem.find_element(By.XPATH, f".//*[contains(@data-e2e, '{stat_type}')]")
            text = stat_elem.text or "0"
            
            # Parse số liệu (xử lý định dạng K, M)
            text = text.lower().strip()
            if 'k' in text:
                return int(float(text.replace('k', '')) * 1000)
            elif 'm' in text:
                return int(float(text.replace('m', '')) * 1000000)
            else:
                return int(''.join(filter(str.isdigit, text)) or 0)
        except:
            return 0

    async def get_trending(self, target_count: int = 3000, autosave_path: Optional[str] = None, autosave_every: int = 100):
        """Lấy video trending."""
        logger.info(f"🔥 Đang lấy tối đa {target_count} video trending...")
        
        try:
            self.driver.get("https://www.tiktok.com/explore")
            time.sleep(5)
            
            videos = self.scroll_to_load_videos(target_count=target_count)
            
            if autosave_path:
                save_json(videos, autosave_path)
            
            return videos

        except Exception as e:
            logger.error(f"Lỗi get_trending: {e}")
            return []

    async def search_videos(self, keyword: str, target_count: int = 3000, autosave_path: Optional[str] = None, autosave_every: int = 100):
        """Tìm kiếm video."""
        logger.info(f"🔍 Đang tìm kiếm '{keyword}' (tối đa {target_count} video)...")
        
        try:
            search_url = f"https://www.tiktok.com/search/video?q={quote(keyword)}"
            self.driver.get(search_url)
            time.sleep(5)
            
            videos = self.scroll_to_load_videos(target_count=target_count)
            
            if autosave_path:
                save_json(videos, autosave_path)
            
            return videos

        except Exception as e:
            logger.error(f"Lỗi search_videos: {e}")
            return []

    async def hashtag_videos(self, hashtag: str, target_count: int = 3000, autosave_path: Optional[str] = None, autosave_every: int = 100):
        """Lấy video từ hashtag."""
        logger.info(f"🏷  Đang lấy video từ hashtag #{hashtag} (tối đa {target_count})...")
        
        try:
            hashtag_url = f"https://www.tiktok.com/tag/{quote(hashtag)}"
            self.driver.get(hashtag_url)
            time.sleep(5)
            
            videos = self.scroll_to_load_videos(target_count=target_count)
            
            if autosave_path:
                save_json(videos, autosave_path)
            
            return videos

        except Exception as e:
            logger.error(f"Lỗi hashtag_videos: {e}")
            return []

    async def user_videos(self, username: str, target_count: int = 3000, autosave_path: Optional[str] = None, autosave_every: int = 100):
        """Lấy video từ user."""
        logger.info(f"👤 Đang lấy video từ @{username} (tối đa {target_count})...")
        
        try:
            user_url = f"https://www.tiktok.com/@{username}"
            self.driver.get(user_url)
            time.sleep(5)
            
            videos = self.scroll_to_load_videos(target_count=target_count)
            
            if autosave_path:
                save_json(videos, autosave_path)
            
            return videos

        except Exception as e:
            logger.error(f"Lỗi user_videos: {e}")
            return []


def save_json(data: List[Dict[str, Any]], filename: str, quiet: bool = False):
    """Lưu dữ liệu vào JSON."""
    os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    if not quiet:
        logger.info(f"💾 Đã lưu {len(data)} video vào file: {filename}")


def print_stats(videos: List[Dict[str, Any]]):
    """In thống kê."""
    if not videos:
        logger.warning("⚠️  Không có video để thống kê")
        return

    total_views = sum(int(v.get("views", 0) or 0) for v in videos)
    total_likes = sum(int(v.get("likes", 0) or 0) for v in videos)
    total_comments = sum(int(v.get("comments", 0) or 0) for v in videos)
    total_shares = sum(int(v.get("shares", 0) or 0) for v in videos)

    n = len(videos)
    logger.info("\n📊 THỐNG KÊ:")
    logger.info(f"   • Số video: {n}")
    logger.info(f"   • Tổng views: {total_views:,}")
    logger.info(f"   • Tổng likes: {total_likes:,}")
    logger.info(f"   • Tổng comments: {total_comments:,}")
    logger.info(f"   • Tổng shares: {total_shares:,}")
    if n > 0:
        logger.info(f"   • TB views/video: {(total_views // n):,}")
        logger.info(f"   • TB likes/video: {(total_likes // n):,}")


async def main():
    """Main function."""
    scraper = TikTokSeleniumScraper(
        headless=True,
        sleep_min=3.0,
        sleep_max=5.0,
        pause_every=50,
        pause_seconds=2.0,
        max_retries=3,
    )

    if not scraper.initialize():
        return

    try:
        logger.info("=" * 70)
        logger.info("1. Trending")
        logger.info("2. Search theo từ khóa")
        logger.info("3. Hashtag")
        logger.info("4. User")
        logger.info("=" * 70)

        choice = input("Chọn chế độ (1-4) [mặc định: 1]: ").strip() or "1"
        target_str = input("Số video tối đa [mặc định: 3000]: ").strip() or "3000"
        target_count = int(target_str)

        autosave_path = "out/tiktok_autosave.json"
        autosave_every = 100

        videos: List[Dict[str, Any]] = []

        if choice == "1":
            videos = await scraper.get_trending(
                target_count=target_count,
                autosave_path=autosave_path,
                autosave_every=autosave_every,
            )

        elif choice == "2":
            kw = input("Nhập từ khóa: ").strip()
            if kw:
                videos = await scraper.search_videos(
                    kw,
                    target_count=target_count,
                    autosave_path=autosave_path,
                    autosave_every=autosave_every,
                )

        elif choice == "3":
            tag = input("Nhập hashtag (không cần #): ").strip()
            if tag:
                videos = await scraper.hashtag_videos(
                    tag,
                    target_count=target_count,
                    autosave_path=autosave_path,
                    autosave_every=autosave_every,
                )

        elif choice == "4":
            username = input("Nhập username (không cần @): ").strip()
            if username:
                videos = await scraper.user_videos(
                    username,
                    target_count=target_count,
                    autosave_path=autosave_path,
                    autosave_every=autosave_every,
                )

        if not videos:
            logger.warning("\n⚠️  Không lấy được video nào.")
            return

        print_stats(videos)

        save = input("\nLưu JSON cuối cùng? (y/n) [mặc định: y]: ").strip().lower()
        if save != "n":
            default_name = f"out/tiktok_{len(videos)}_videos.json"
            filename = input(f"Tên file [mặc định: {default_name}]: ").strip() or default_name
            save_json(videos, filename)

    finally:
        logger.info("\n🔄 Đóng WebDriver...")
        scraper.close()
        logger.info("✓ Xong!")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

