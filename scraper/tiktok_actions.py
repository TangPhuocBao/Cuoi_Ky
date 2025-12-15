from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
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
                "comments_data": []  # Thêm trường comments_data trống
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

    def get_video_comments(self, video_url: str, max_comments: int = 100) -> List[Dict[str, Any]]:
        """
        Lấy danh sách comment từ một video TikTok.
        
        Args:
            video_url: URL của video TikTok
            max_comments: Số lượng comment tối đa cần lấy
            
        Returns:
            Danh sách comment với thông tin chi tiết
        """
        logger.info(f"💬 Đang lấy comment từ video: {video_url}")
        comments = []
        
        try:
            # Mở video trong tab mới
            original_window = self.driver.current_window_handle
            self.driver.execute_script("window.open('');")
            self.driver.switch_to.window(self.driver.window_handles[-1])
            
            self.driver.get(video_url)
            time.sleep(5)  # Chờ trang tải
            
            # Cuộn xuống để load comment section
            self.driver.execute_script("window.scrollBy(0, 800);")
            time.sleep(2)
            
            # Tìm và click vào phần comment để mở rộng
            try:
                # Thử tìm nút xem thêm comment
                comment_section = self.driver.find_element(By.CSS_SELECTOR, "[data-e2e='comment-container']")
                comment_section.click()
                time.sleep(2)
            except:
                logger.debug("Không tìm thấy nút comment, tiếp tục...")
            
            # Scroll để load thêm comment
            scroll_attempts = 0
            max_scroll_attempts = 20
            
            while len(comments) < max_comments and scroll_attempts < max_scroll_attempts:
                # Tìm tất cả comment elements
                try:
                    comment_elements = self.driver.find_elements(By.CSS_SELECTOR, "[data-e2e='comment-item']")
                    
                    for comment_elem in comment_elements:
                        if len(comments) >= max_comments:
                            break
                            
                        try:
                            comment_info = self._parse_comment_element(comment_elem)
                            if comment_info:
                                # Kiểm tra comment đã tồn tại chưa
                                comment_id = comment_info.get("comment_id")
                                if comment_id and comment_id not in [c.get("comment_id") for c in comments]:
                                    comments.append(comment_info)
                                    logger.debug(f"Đã lấy comment {len(comments)}/{max_comments}: {comment_info.get('text', '')[:50]}...")
                        except Exception as e:
                            logger.debug(f"Lỗi parse comment: {e}")
                            continue
                            
                except Exception as e:
                    logger.debug(f"Không tìm thấy comment elements: {e}")
                
                # Scroll xuống để load thêm comment
                self.driver.execute_script("window.scrollBy(0, 300);")
                scroll_attempts += 1
                time.sleep(1)
                
                # Kiểm tra xem có thêm comment mới không
                if len(comment_elements) >= max_comments:
                    break
            
            logger.info(f"✓ Đã lấy {len(comments)} comment từ video")
            
            # Đóng tab và quay lại tab gốc
            self.driver.close()
            self.driver.switch_to.window(original_window)
            
            return comments
            
        except Exception as e:
            logger.error(f"✗ Lỗi khi lấy comment: {e}")
            
            # Cố gắng quay lại tab gốc nếu có lỗi
            try:
                if len(self.driver.window_handles) > 1:
                    self.driver.close()
                self.driver.switch_to.window(original_window)
            except:
                pass
                
            return comments

    def _parse_comment_element(self, comment_elem) -> Optional[Dict[str, Any]]:
        """Parse thông tin từ một comment element."""
        try:
            # Lấy comment ID
            comment_id = comment_elem.get_attribute("data-comment-id") or ""
            if not comment_id:
                # Tạo ID từ timestamp nếu không có
                comment_id = f"comment_{int(time.time() * 1000)}"
            
            # Lấy tên người comment
            try:
                username_elem = comment_elem.find_element(By.CSS_SELECTOR, "[data-e2e='comment-username']")
                username = username_elem.text or ""
            except:
                username = ""
            
            # Lấy nội dung comment
            try:
                text_elem = comment_elem.find_element(By.CSS_SELECTOR, "[data-e2e='comment-text']")
                text = text_elem.text or ""
            except:
                text = ""
            
            # Lấy số like của comment
            try:
                likes_elem = comment_elem.find_element(By.CSS_SELECTOR, "[data-e2e='comment-like-count']")
                likes_text = likes_elem.text or "0"
                likes = int(''.join(filter(str.isdigit, likes_text)) or 0)
            except:
                likes = 0
            
            # Lấy thời gian comment
            try:
                time_elem = comment_elem.find_element(By.CSS_SELECTOR, "[data-e2e='comment-time']")
                time_text = time_elem.text or ""
            except:
                time_text = ""
            
            # Lấy link avatar (nếu có)
            try:
                avatar_elem = comment_elem.find_element(By.CSS_SELECTOR, "img[src*='tiktok']")
                avatar_url = avatar_elem.get_attribute("src") or ""
            except:
                avatar_url = ""
            
            # Kiểm tra xem có phải tác giả video comment không
            is_author = False
            try:
                author_badge = comment_elem.find_element(By.CSS_SELECTOR, "[data-e2e='comment-author-badge']")
                is_author = bool(author_badge)
            except:
                pass
            
            # Tạo timestamp
            timestamp = int(time.time())
            
            return {
                "comment_id": comment_id,
                "username": username,
                "text": text,
                "likes": likes,
                "time_text": time_text,
                "avatar_url": avatar_url,
                "is_author": is_author,
                "timestamp": timestamp,
                "collected_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            }
            
        except Exception as e:
            logger.debug(f"Lỗi parse comment element: {e}")
            return None

    async def get_videos_with_comments(
        self, 
        mode: str = "trending", 
        keyword: str = "", 
        target_videos: int = 10, 
        comments_per_video: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Lấy video kèm theo comment của mỗi video.
        
        Args:
            mode: Chế độ lấy video ('trending', 'search', 'hashtag', 'user')
            keyword: Từ khóa tìm kiếm hoặc username/hashtag tùy mode
            target_videos: Số video tối đa cần lấy
            comments_per_video: Số comment tối đa cho mỗi video
            
        Returns:
            Danh sách video với comment đầy đủ
        """
        logger.info(f"🎯 Lấy {target_videos} video với {comments_per_video} comment mỗi video")
        
        # Lấy danh sách video
        videos = []
        if mode == "trending":
            videos = await self.get_trending(target_count=target_videos)
        elif mode == "search":
            videos = await self.search_videos(keyword, target_count=target_videos)
        elif mode == "hashtag":
            videos = await self.hashtag_videos(keyword, target_count=target_videos)
        elif mode == "user":
            videos = await self.user_videos(keyword, target_count=target_videos)
        
        # Lấy comment cho từng video
        for i, video in enumerate(videos):
            logger.info(f"📥 Đang lấy comment cho video {i+1}/{len(videos)}: {video.get('video_id', '')}")
            
            video_url = video.get("video_url")
            if video_url:
                comments = self.get_video_comments(video_url, max_comments=comments_per_video)
                video["comments_data"] = comments
                video["total_comments_collected"] = len(comments)
                
                # In thông tin tóm tắt
                if comments:
                    logger.info(f"   ✓ Đã lấy {len(comments)} comment")
                    for j, comment in enumerate(comments[:3]):  # Hiển thị 3 comment đầu
                        logger.info(f"      {j+1}. @{comment.get('username', '')}: {comment.get('text', '')[:50]}...")
                    if len(comments) > 3:
                        logger.info(f"      ... và {len(comments) - 3} comment khác")
            else:
                logger.warning(f"   ✗ Video không có URL")
            
            # Dừng giữa các video để tránh bị block
            if i < len(videos) - 1:
                sleep_time = random.uniform(5, 10)
                logger.info(f"⏳ Chờ {sleep_time:.1f}s trước khi lấy video tiếp theo...")
                time.sleep(sleep_time)
        
        return videos

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
    
    # Tính tổng comment đã thu thập
    total_comments_collected = sum(len(v.get("comments_data", [])) for v in videos)

    n = len(videos)
    logger.info("\n📊 THỐNG KÊ:")
    logger.info(f"   • Số video: {n}")
    logger.info(f"   • Tổng views: {total_views:,}")
    logger.info(f"   • Tổng likes: {total_likes:,}")
    logger.info(f"   • Tổng comments (theo video): {total_comments:,}")
    logger.info(f"   • Tổng shares: {total_shares:,}")
    logger.info(f"   • Tổng comment đã thu thập: {total_comments_collected:,}")
    
    if n > 0:
        logger.info(f"   • TB views/video: {(total_views // n):,}")
        logger.info(f"   • TB likes/video: {(total_likes // n):,}")
        logger.info(f"   • TB comment thu thập/video: {(total_comments_collected // n):,}")


async def main():
    """Main function."""
    scraper = TikTokSeleniumScraper(
        headless=False,  # Để headless=False để dễ debug khi lấy comment
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
        logger.info("5. Lấy video với comment (chế độ nâng cao)")
        logger.info("=" * 70)

        choice = input("Chọn chế độ (1-5) [mặc định: 1]: ").strip() or "1"
        
        if choice == "5":
            # Chế độ lấy video với comment
            logger.info("\n🎯 CHẾ ĐỘ LẤY VIDEO VỚI COMMENT")
            logger.info("1. Trending")
            logger.info("2. Search theo từ khóa")
            logger.info("3. Hashtag")
            logger.info("4. User")
            
            mode_choice = input("Chọn nguồn video (1-4) [mặc định: 1]: ").strip() or "1"
            
            mode_map = {"1": "trending", "2": "search", "3": "hashtag", "4": "user"}
            mode = mode_map.get(mode_choice, "trending")
            
            keyword = ""
            if mode in ["search", "hashtag", "user"]:
                prompt_text = {
                    "search": "Nhập từ khóa tìm kiếm",
                    "hashtag": "Nhập hashtag (không cần #)",
                    "user": "Nhập username (không cần @)"
                }
                keyword = input(f"{prompt_text[mode]}: ").strip()
            
            target_videos = int(input("Số video tối đa [mặc định: 10]: ").strip() or "10")
            comments_per_video = int(input("Số comment tối đa mỗi video [mặc định: 20]: ").strip() or "20")
            
            videos = await scraper.get_videos_with_comments(
                mode=mode,
                keyword=keyword,
                target_videos=target_videos,
                comments_per_video=comments_per_video
            )
            
        else:
            # Chế độ cũ chỉ lấy video
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

        # Hiển thị comment statistics
        total_comments = sum(len(v.get("comments_data", [])) for v in videos)
        if total_comments > 0:
            logger.info("\n💬 THỐNG KÊ COMMENT:")
            logger.info(f"   • Tổng số comment thu thập: {total_comments}")
            
            # Tìm video có nhiều comment nhất
            max_comments_video = max(videos, key=lambda x: len(x.get("comments_data", [])))
            max_comments = len(max_comments_video.get("comments_data", []))
            logger.info(f"   • Video nhiều comment nhất: {max_comments} comment")
            
            # Hiển thị một số comment mẫu
            logger.info("\n📝 COMMENT MẪU:")
            for i, video in enumerate(videos[:3]):  # Lấy 3 video đầu
                comments = video.get("comments_data", [])
                if comments:
                    logger.info(f"\nVideo {i+1} ({video.get('video_id', '')}):")
                    for j, comment in enumerate(comments[:2]):  # 2 comment đầu mỗi video
                        logger.info(f"   {j+1}. @{comment.get('username', '')}: {comment.get('text', '')[:80]}...")

        save = input("\nLưu JSON cuối cùng? (y/n) [mặc định: y]: ").strip().lower()
        if save != "n":
            default_name = f"out/tiktok_{len(videos)}_videos_with_comments.json" if total_comments > 0 else f"out/tiktok_{len(videos)}_videos.json"
            filename = input(f"Tên file [mặc định: {default_name}]: ").strip() or default_name
            save_json(videos, filename)

    finally:
        logger.info("\n🔄 Đóng WebDriver...")
        scraper.close()
        logger.info("✓ Xong!")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
