import time
import json
import os
import re
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException

from browser import create_driver


OUT_DIR = "out"
SCROLL_PAUSE = 2
MAX_SCROLL = 200


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class TikTokSeleniumScraper:
    def __init__(self):
        self.driver = create_driver()
        self.videos = {}
        os.makedirs(OUT_DIR, exist_ok=True)

    def close(self):
        self.driver.quit()

    def collect_video_links(self):
        links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/video/']")
        for a in links:
            try:
                url = a.get_attribute("href").split("?")[0]
                vid = url.split("/video/")[-1]
                if vid not in self.videos:
                    self.videos[vid] = {
                        "video_id": vid,
                        "video_url": url,
                        "collected_at": now(),
                    }
            except StaleElementReferenceException:
                continue

    def scroll_and_collect(self, url, target=1000):
        print(f" Open {url}")
        self.driver.get(url)
        time.sleep(6)

        for i in range(MAX_SCROLL):
            self.collect_video_links()
            print(f"Scroll {i+1} | collected={len(self.videos)}")

            if len(self.videos) >= target:
                break

            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);"
            )
            time.sleep(SCROLL_PAUSE)

        self._save("step1_video_links.json")


    def extract_json_state(self):
        scripts = self.driver.find_elements(By.TAG_NAME, "script")
        for s in scripts:
            txt = s.get_attribute("innerHTML")
            if txt and "ItemModule" in txt and "UserModule" in txt:
                try:
                    match = re.search(r"\{.*\}", txt, re.S)
                    if match:
                        return json.loads(match.group())
                except Exception:
                    pass
        return None
    def scrape_video_detail(self, url):
        self.driver.get(url)
        time.sleep(5)

        data = {
            "video_url": url,
            "scraped_at": now(),
        }

        state = self.extract_json_state()
        if not state:
            data["error"] = "NO_STATE_JSON"
            return data

        item = list(state.get("ItemModule", {}).values())[0]
        stats = item.get("stats", {})
        author = item.get("author", {})
        desc = item.get("desc", "")

        data.update({
            "video_id": item.get("id"),
            "author": author,
            "description": desc,
            "hashtags": re.findall(r"#(\w+)", desc),
            "likes": stats.get("diggCount"),
            "comments": stats.get("commentCount"),
            "shares": stats.get("shareCount"),
            "views": stats.get("playCount"),
        })

        # COMMENT
        comments = []
        comment_mod = state.get("CommentItem", {})
        for c in comment_mod.values():
            comments.append({
                "comment_id": c.get("id"),
                "text": c.get("text"),
                "likes": c.get("diggCount"),
                "author": c.get("user", {}).get("uniqueId"),
                "create_time": c.get("createTime"),
            })

        data["comment_list"] = comments
        data["num_comments_collected"] = len(comments)

        return data

    def scrape_all_videos(self, limit=None):
        results = []
        items = list(self.videos.values())
        if limit:
            items = items[:limit]

        for i, v in enumerate(items, 1):
            print(f"🎬 [{i}/{len(items)}] {v['video_url']}")
            info = self.scrape_video_detail(v["video_url"])
            results.append(info)

            if i % 20 == 0:
                self._save("autosave_full.json", results)

        self._save("tiktok_full_data.json", results)
        return results

    def _save(self, name, data=None):
        path = os.path.join(OUT_DIR, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data if data is not None else list(self.videos.values()),
                      f, ensure_ascii=False, indent=2)
        print(f"💾 Saved → {path}")


# MAIN
def main():
    scraper = TikTokSeleniumScraper()

    try:
        print("1. Trending")
        print("2. Hashtag")
        print("3. User")
        c = input("Chọn (1-3): ").strip() or "1"

        if c == "1":
            url = "https://www.tiktok.com/foryou"
        elif c == "2":
            tag = input("Hashtag: ").strip()
            url = f"https://www.tiktok.com/tag/{tag}"
        else:
            user = input("Username: ").strip()
            url = f"https://www.tiktok.com/@{user}"

        scraper.scroll_and_collect(url, target=1000)
        scraper.scrape_all_videos(limit=1000)

    finally:
        scraper.close()


if __name__ == "__main__":
    main()
