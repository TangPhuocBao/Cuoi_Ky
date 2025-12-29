import undetected_chromedriver as uc
import time
import random
import csv
import os
import logging
import requests

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ================= CONFIG =================
TARGET_PROFILE = "https://www.tiktok.com/explore"
LIMIT_VIDEOS = 200
MAX_COMMENTS_PER_VIDEO = 100

VIDEO_FILE = "tiktok_videos.csv"
COMMENT_FILE = "tiktok_comments.csv"

# ================= LOGGING =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# SELENIUM
def setup_driver():
    options = uc.ChromeOptions()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    user_data_dir = os.path.join(script_dir, "tiktok_session")
    
    if not os.path.exists(user_data_dir):
        os.makedirs(user_data_dir)
        
    options.add_argument(f"--user-data-dir={user_data_dir}") # giữ đăng nhập
    options.add_argument("--profile-directory=Default")  # chọn profile mặc định
    options.add_argument("--start-maximized") # Mở toàn màn hình
    options.add_argument("--disable-notifications") # tắt thông báo
    options.add_argument("--mute-audio") # tắt âm thanh

    driver = uc.Chrome(options=options)
    return driver


def solve_captcha(driver):
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CLASS_NAME, "captcha_verify_container"))
        )
        logger.warning("CAPTCHA phát hiện – vui lòng giải tay")
        WebDriverWait(driver, 300).until_not(
            EC.presence_of_element_located((By.CLASS_NAME, "captcha_verify_container"))
        )
        logger.info("CAPTCHA đã giải")
    except:
        pass

# ================= VIDEO LINKS =================
def scroll_get_video_links(driver, limit):
    logger.info(f"Truy cập: {TARGET_PROFILE}")
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

        logger.info(f"Đã lấy {len(links)}/{limit} video")

        if len(links) >= limit:
            break

    return list(links)[:limit]


# ================= VIDEO INFO =================
def get_video_info(driver, url):
    driver.get(url)
    time.sleep(4)
    solve_captcha(driver)

    # Lấy ID từ URL
    try:
        video_id = url.split("/video/")[-1].split("?")[0]
    except:
        video_id = "unknown"

    data = {
        "video_url": url,
        "video_id": video_id,
        "caption": "",
        "like_count": "0",
        "comment_count": "0",
        "share_count": "0",
        "save_count": "0" # Thêm cái này vì TikTok hay có nút Save
    }

    # 1. Lấy Caption (Mô tả)
    try:
        # data-e2e="video-desc" là chuẩn nhất
        caption = driver.find_element(By.CSS_SELECTOR, '[data-e2e="video-desc"]')
        data["caption"] = caption.text
    except:
        pass

    # 2. Lấy Like Count
    try:
        like = driver.find_element(By.CSS_SELECTOR, '[data-e2e="like-count"]')
        data["like_count"] = like.text
    except:
        pass

    # 3. Lấy Comment Count
    try:
        comment = driver.find_element(By.CSS_SELECTOR, '[data-e2e="comment-count"]')
        data["comment_count"] = comment.text
    except:
        pass

    # 4. Lấy Share Count
    try:
        share = driver.find_element(By.CSS_SELECTOR, '[data-e2e="share-count"]')
        data["share_count"] = share.text
    except:
        pass
        
    # 5. Lấy Save/Bookmark Count (Tùy chọn)
    try:
        save = driver.find_element(By.CSS_SELECTOR, '[data-e2e="undefined-count"]') # TikTok đôi khi đổi cái này, nhưng thường là format count
        # Hoặc tìm thẻ cha chứa icon bookmark
        pass 
    except:
        pass

    logger.info(
        f"{video_id} |{data['like_count']} | {data['comment_count']} | {data['share_count']}"
    )
    return data

# ================= GET COMMENTS =================
def get_comments(driver, video_id, max_cmt):
    comments_data = []
    logger.info(f"⬇Đang xử lý video: {video_id}")

    # --- 1. CLICK MỞ COMMENT
    clicked = False
    selectors = [
        (By.ID, "comments"),
        (By.CSS_SELECTOR, 'button[data-e2e="comment-icon"]'),
        (By.XPATH, "//button[contains(., 'Comments')]"),
        (By.CSS_SELECTOR, '.TUXTabBar-itemTitle')
    ]

    for method, selector in selectors:
        try:
            element = WebDriverWait(driver, 3).until(EC.presence_of_element_located((method, selector)))
            # Thử click bằng ActionChains
            from selenium.webdriver.common.action_chains import ActionChains
            actions = ActionChains(driver)
            actions.move_to_element(element).click().perform()
            # Click bồi thêm bằng JS cho chắc chắn
            driver.execute_script("arguments[0].click();", element)
            clicked = True
            logger.info(f"Đã mở bảng bình luận.")
            break
        except:
            continue

    if not clicked:
        try:
            driver.execute_script("document.elementFromPoint(window.innerWidth - 50, window.innerHeight / 2).click();")
        except: pass

    time.sleep(3) 

    # --- 2. LOGIC CÀO VÀ FIX LỖI ĐỢI KHI HẾT COMMENT ---
    collected_texts = set()
    retries = 0
    last_all_items_count = 0  # Biến quan trọng để kiểm tra chạm đáy
    
    while len(comments_data) < max_cmt:
        # Lấy tất cả item đang có trên màn hình
        all_items = driver.find_elements(By.CSS_SELECTOR, '[data-e2e="comment-level-1"]')
        current_all_count = len(all_items)

        # KIỂM TRA CHẠM ĐÁY: Nếu sau khi scroll mà số lượng phần tử không đổi
        if current_all_count == last_all_items_count and current_all_count > 0:
            retries += 1
            logger.info(f"Đang cuộn tìm thêm... (Lần thử {retries}/5)")
            if retries >= 5: # Nếu thử 5 lần không thấy có thêm cmt mới -> Thoát
                logger.info(f"Đã hết bình luận thực tế trên video này.")
                break
        else:
            if current_all_count > last_all_items_count:
                retries = 0 # Reset nếu vẫn thấy có thêm dữ liệu mới
            last_all_items_count = current_all_count

        if not all_items:
            driver.execute_script("window.scrollBy(0, 500);")
            time.sleep(2)
            retries += 1
            if retries > 10: break
            continue

        # Duyệt qua các item để lấy text mới
        new_found_in_loop = False
        for item in all_items:
            try:
                # Lấy text nội dung bình luận
                try:
                    raw_text = item.find_element(By.CSS_SELECTOR, '[data-e2e="comment-level-1-content"]').text.strip()
                except:
                    raw_text = item.text.split('\n')[0].strip() # Fallback

                if not raw_text or raw_text in collected_texts: 
                    continue
                
                # Lấy User Nickname
                try:
                    user_elem = item.find_element(By.CSS_SELECTOR, '[data-e2e="comment-username"]')
                    user = user_elem.text.strip()
                except:
                    # Cách XPath dự phòng của bạn
                    try:
                        user_elem = item.find_element(By.XPATH, ".//ancestor::div[contains(@class,'DivContentContainer')]//a[contains(@href, '/@')]")
                        user = user_elem.get_attribute("href").split("/@")[-1].split("?")[0]
                    except:
                        user = "unknown"

                collected_texts.add(raw_text)
                comments_data.append({
                    "video_id": video_id,
                    "user": user,
                    "text": raw_text.replace('\n', ' ')
                })
                new_found_in_loop = True
                print(f"   + [{len(comments_data)}] {user}: {raw_text[:30]}...")

                if len(comments_data) >= max_cmt:
                    break
            except:
                continue

        # Scroll tới phần tử cuối cùng để kích hoạt load thêm
        if all_items:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", all_items[-1])
        
        time.sleep(random.uniform(1.5, 2.5))

    logger.info(f"Hoàn thành lấy {len(comments_data)} bình luận.")
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
        logger.info("Khởi động trình duyệt...")
        driver = setup_driver()
        
        # 1. LẤY LINK VIDEO
        logger.info(f"Bắt đầu lấy {LIMIT_VIDEOS} video...")
        video_links = scroll_get_video_links(driver, LIMIT_VIDEOS)
        
        if not video_links:
            logger.error("Không lấy được link video nào!")
        else:
            logger.info(f"Lấy được {len(video_links)} link video")
            
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
                        logger.info("Video này không có comment")
                    
                    # Delay giữa các video
                    time.sleep(random.uniform(3, 5))
                    
                except Exception as e:
                    logger.error(f"Lỗi xử lý video: {e}")
                    continue
        
        logger.info("\n" + "="*50)
        logger.info("HOÀN THÀNH!")
        logger.info(f"Video file: {VIDEO_FILE}")
        logger.info(f"Comment file: {COMMENT_FILE}")
        logger.info("="*50)
        
    except Exception as e:
        logger.error(f"Lỗi chung: {e}")
        
    finally:
        if driver:
            logger.info("Đóng trình duyệt...")
            time.sleep(3)
            driver.quit()