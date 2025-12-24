import undetected_chromedriver as uc
import time
import random
import csv
import os
import logging
import requests as re

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ================= CONFIG =================
TARGET_PROFILE = "https://www.tiktok.com/explore"
LIMIT_VIDEOS = 20  
MAX_COMMENTS_PER_VIDEO = 30

VIDEO_FILE = "tiktok_videos.csv"
COMMENT_FILE = "tiktok_comments.csv"

# ================= LOGGING =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)




# ================= NUMBER PARSER =================
def parse_tiktok_number(text: str):
    """
    Convert TikTok abbreviated numbers to int.
    Examples:
      "1.2K" -> 1200
      "3.4M" -> 3400000
      "567"  -> 567
    Works with aria-label strings too.
    """
    if not text:
        return 0
    s = str(text).strip().lower().replace(",", "")
    # Grab first token that looks like a number (e.g., "1.2k", "34", "0")
    # TikTok often formats like "1.2M likes" or "1.2m"
    token_match = re.search(r"(\d+(?:\.\d+)?)(\s*[km])?", s)
    if not token_match:
        return 0
    num = float(token_match.group(1))
    suffix = (token_match.group(2) or "").strip()
    if suffix == "k":
        num *= 1_000
    elif suffix == "m":
        num *= 1_000_000
    try:
        return int(num)
    except:
        return 0
# ================= SELENIUM =================
def setup_driver():
    options = uc.ChromeOptions()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    user_data_dir = os.path.join(script_dir, "tiktok_session")
    
    if not os.path.exists(user_data_dir):
        os.makedirs(user_data_dir)
        
    options.add_argument(f"--user-data-dir={user_data_dir}")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_argument("--mute-audio")

    driver = uc.Chrome(options=options)
    return driver


def solve_captcha(driver):
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CLASS_NAME, "captcha_verify_container"))
        )
        logger.warning("⚠️ CAPTCHA phát hiện – vui lòng giải tay")
        WebDriverWait(driver, 300).until_not(
            EC.presence_of_element_located((By.CLASS_NAME, "captcha_verify_container"))
        )
        logger.info("✅ CAPTCHA đã giải")
    except:
        pass

# ================= VIDEO LINKS =================
def scroll_get_video_links(driver, limit):
    logger.info(f"🌍 Truy cập: {TARGET_PROFILE}")
    driver.get(TARGET_PROFILE)
    time.sleep(5)
    solve_captcha(driver)

    links = set()
    no_new_count = 0

    while len(links) < limit and no_new_count < 5:
        driver.execute_script("window.scrollBy(0, 800)")
        time.sleep(random.uniform(2, 3))

        elems = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/video/"]')
        prev_len = len(links)
        
        for e in elems:
            href = e.get_attribute("href")
            if href and "/video/" in href:
                links.add(href)

        if len(links) > prev_len:
            no_new_count = 0
        else:
            no_new_count += 1

        logger.info(f"📹 Đã lấy {len(links)}/{limit} video")

        if len(links) >= limit:
            break

    return list(links)[:limit]


# ================= VIDEO INFO =================
def get_video_info(driver, url):
    driver.get(url)
    time.sleep(4)
    solve_captcha(driver)

    video_id = url.split("/video/")[-1].split("?")[0]

    data = {
        "video_url": url,
        "video_id": video_id,
        "caption": "",
        "like_count": 0,
        "comment_count": 0,
        "share_count": 0,
    }

    # Caption
    try:
        caption = driver.find_element(By.CSS_SELECTOR, '[data-e2e="video-desc"]')
        data["caption"] = caption.text[:200]
    except:
        pass

    def safe_get_text(selector: str) -> str:
        try:
            return driver.find_element(By.CSS_SELECTOR, selector).text.strip()
        except:
            return ""

    like_text = safe_get_text('strong[data-e2e="like-count"]')
    comment_text = safe_get_text('strong[data-e2e="comment-count"]')
    share_text = safe_get_text('strong[data-e2e="share-count"]')

    if not like_text or not comment_text or not share_text:
        try:
            action_bar = driver.find_element(By.CSS_SELECTOR, '[data-e2e="browse-like-count"], [data-e2e="video-player"], body')
            buttons = action_bar.find_elements(By.TAG_NAME, "button")
        except:
            buttons = driver.find_elements(By.TAG_NAME, "button")

        for b in buttons:
            aria = (b.get_attribute("aria-label") or "").lower()
            if not aria:
                continue

            if (not like_text) and any(x in aria for x in ["like", "thích"]):
                like_text = aria
            elif (not comment_text) and any(x in aria for x in ["comment", "bình luận"]):
                comment_text = aria
            elif (not share_text) and any(x in aria for x in ["share", "chia sẻ"]):
                share_text = aria

    data["like_count"] = parse_tiktok_number(like_text)
    data["comment_count"] = parse_tiktok_number(comment_text)
    data["share_count"] = parse_tiktok_number(share_text)

    logger.info(
        f"🎬 {video_id} | ❤️ {data['like_count']} | 💬 {data['comment_count']} | 🔁 {data['share_count']}"
    )
    return data

# ================= GET COMMENTS =================
def get_comments(driver, video_id, max_cmt):
    comments_data = []
    logger.info(f"⬇️ Đang tìm cách click mở comment...")

    # --- PHƯƠNG PHÁP CLICK ĐA TẦNG ---
    clicked = False
    selectors = [
        (By.ID, "comments"),
        (By.CSS_SELECTOR, 'button[data-e2e="comment-icon"]'),
        (By.XPATH, "//button[contains(., 'Comments')]"),
        (By.CSS_SELECTOR, '.TUXTabBar-itemTitle')
    ]

    for method, selector in selectors:
        try:
            # Đợi phần tử hiện diện
            element = WebDriverWait(driver, 3).until(EC.presence_of_element_located((method, selector)))
            
            # 1. Thử di chuyển chuột tới rồi click
            from selenium.webdriver.common.action_chains import ActionChains
            actions = ActionChains(driver)
            actions.move_to_element(element).click().perform()
            
            # 2. Nếu không được, dùng JavaScript ép click (mạnh nhất)
            driver.execute_script("arguments[0].scrollIntoView(true);", element)
            driver.execute_script("arguments[0].click();", element)
            
            logger.info(f"✅ Đã click thành công bằng selector: {selector}")
            clicked = True
            break
        except:
            continue

    if not clicked:
        logger.warning("⚠️ Không thể click bằng code, thử click bằng tọa độ màn hình...")
        # Tuyệt chiêu cuối: Click vào vị trí cố định của nút comment trên UI Desktop
        try:
            driver.execute_script("document.elementFromPoint(window.innerWidth - 50, window.innerHeight / 2).click();")
        except: pass

    time.sleep(3) # Chờ bảng comment bung ra

    # --- BẮT ĐẦU CÀO ---
    collected_texts = set()
    retries = 0
    
    while len(comments_data) < max_cmt and retries < 15:
        # TikTok thường thay đổi class, dùng data-e2e là chuẩn nhất 2025
        items = driver.find_elements(By.CSS_SELECTOR, '[data-e2e="comment-level-1"]')
        
        if not items:
            # Cuộn cả trang và cuộn container nếu có
            driver.execute_script("window.scrollBy(0, 500);")
            time.sleep(2)
            retries += 1
            continue

        new_found = False
        for item in items:
            try:
                text = item.text.strip()
                if not text or text in collected_texts: continue
                
                # XPath chuẩn để lấy user trong cấu trúc DivContentContainer
                try:
                    user_elem = item.find_element(By.XPATH, ".//ancestor::div[contains(@class,'DivContentContainer')]//a[contains(@href, '/@')]")
                    user = user_elem.get_attribute("href").split("/@")[-1].split("?")[0]
                except:
                    user = "unknown"

                collected_texts.add(text)
                comments_data.append({"video_id": video_id, "user": user, "text": text.replace("\n", " ")})
                new_found = True
                print(f"   + {user}: {text[:30]}...")

                if len(comments_data) >= max_cmt: break
            except: continue

        if items:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", items[-1])
            retries = 0
        
        time.sleep(random.uniform(2, 4))
        if not new_found: retries += 1

    return comments_data

# ================= CSV =================
def save_csv(file, rows, headers):
    exists = os.path.isfile(file)
    with open(file, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if not exists:
            writer.writeheader()
        if isinstance(rows, list):
            writer.writerows(rows)
        else:
            writer.writerow(rows)


# ================= MAIN =================
if __name__ == "__main__":
    driver = None
    
    try:
        logger.info("🚀 Khởi động trình duyệt...")
        driver = setup_driver()
        
        # 1. LẤY LINK VIDEO
        logger.info(f"📺 Bắt đầu lấy {LIMIT_VIDEOS} video...")
        video_links = scroll_get_video_links(driver, LIMIT_VIDEOS)
        
        if not video_links:
            logger.error("❌ Không lấy được link video nào!")
        else:
            logger.info(f"✅ Lấy được {len(video_links)} link video")
            
            # 2. DUYỆT MỖI VIDEO
            for idx, video_url in enumerate(video_links, 1):
                logger.info(f"\n[{idx}/{len(video_links)}] 🎬 Đang xử lý: {video_url}")
                
                try:
                    # Lấy info video
                    video_info = get_video_info(driver, video_url)
                    save_csv(VIDEO_FILE, video_info, video_info.keys())
                    
                    # Lấy comment
                    if video_info['comment_count'] and int(video_info['comment_count']) > 0:
                        comments = get_comments(driver, video_info['video_id'], MAX_COMMENTS_PER_VIDEO)
                        if comments:
                            save_csv(COMMENT_FILE, comments, comments[0].keys())
                    else:
                        logger.info("   ℹ️ Video này không có comment")
                    
                    # Delay giữa các video
                    time.sleep(random.uniform(3, 5))
                    
                except Exception as e:
                    logger.error(f"❌ Lỗi xử lý video: {e}")
                    continue
        
        logger.info("\n" + "="*50)
        logger.info("✅ HOÀN THÀNH!")
        logger.info(f"📄 Video file: {VIDEO_FILE}")
        logger.info(f"💬 Comment file: {COMMENT_FILE}")
        logger.info("="*50)
        
    except Exception as e:
        logger.error(f"❌ Lỗi chung: {e}")
        
    finally:
        if driver:
            logger.info("👋 Đóng trình duyệt...")
            time.sleep(3)
            driver.quit()