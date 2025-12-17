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
TARGET_PROFILE = "https://www.tiktok.com/"
LIMIT_VIDEOS = 5
MAX_COMMENTS_PER_VIDEO = 50

VIDEO_FILE = "tiktok_videos.csv"
COMMENT_FILE = "tiktok_comments.csv"

# ================= LOGGING =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ================= SELENIUM =================
def setup_driver():
    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    return uc.Chrome(options=options)


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


def get_cookie_dict(driver):
    cookies = driver.get_cookies()
    return {c["name"]: c["value"] for c in cookies}


# ================= VIDEO LINKS =================
def scroll_get_video_links(driver, limit):
    driver.get(TARGET_PROFILE)
    time.sleep(5)
    solve_captcha(driver)

    links = set()

    while len(links) < limit:
        driver.execute_script("window.scrollBy(0, 800)")
        time.sleep(random.uniform(2, 3))

        elems = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/video/"]')
        for e in elems:
            href = e.get_attribute("href")
            if href and "/video/" in href:
                links.add(href)

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
        "like_count": "",
        "comment_count": "",
        "share_count": "",
    }

    try:
        caption = driver.find_element(By.CSS_SELECTOR, '[data-e2e="video-desc"]')
        data["caption"] = caption.text
    except:
        pass

    buttons = driver.find_elements(By.TAG_NAME, "button")
    for b in buttons:
        aria = (b.get_attribute("aria-label") or "").lower()
        num = "".join(filter(str.isdigit, aria))

        if "like" in aria or "thích" in aria:
            data["like_count"] = num
        if "comment" in aria or "bình luận" in aria:
            data["comment_count"] = num
        if "share" in aria or "chia sẻ" in aria:
            data["share_count"] = num

    logger.info(
        f"🎬 {video_id} | ❤️ {data['like_count']} | 💬 {data['comment_count']}"
    )
    return data


# ================= TIKTOK API COMMENT =================
def fetch_comments_api(video_id, cookies, user_agent, max_comments=50):
    url = "https://www.tiktok.com/api/comment/list/"
    headers = {
        "User-Agent": user_agent,
        "Referer": f"https://www.tiktok.com/video/{video_id}",
    }

    params = {
        "aid": 1988,
        "aweme_id": video_id,
        "count": 20,
        "cursor": 0,
    }

    comments = []

    while len(comments) < max_comments:
        r = requests.get(url, headers=headers, cookies=cookies, params=params)
        if r.status_code != 200:
            break

        data = r.json()
        if "comments" not in data:
            break

        for c in data["comments"]:
            comments.append({
                "video_id": video_id,
                "user": c["user"]["nickname"],
                "comment_text": c["text"]
            })

        if not data.get("has_more"):
            break

        params["cursor"] = data["cursor"]
        time.sleep(1)

    logger.info(f"💬 Lấy được {len(comments)} comment")
    return comments


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
def main():
    driver = setup_driver()
    user_agent = driver.execute_script("return navigator.userAgent")

    try:
        logger.info("🚀 BẮT ĐẦU")
        video_links = scroll_get_video_links(driver, LIMIT_VIDEOS)
        cookies = get_cookie_dict(driver)

        for idx, url in enumerate(video_links, 1):
            logger.info(f"\n[{idx}] {url}")
            video = get_video_info(driver, url)
            save_csv(VIDEO_FILE, video, video.keys())

            comments = fetch_comments_api(
                video["video_id"],
                cookies,
                user_agent,
                MAX_COMMENTS_PER_VIDEO
            )
            if comments:
                save_csv(COMMENT_FILE, comments, comments[0].keys())

            time.sleep(random.uniform(5, 8))

        logger.info("✅ HOÀN THÀNH")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
