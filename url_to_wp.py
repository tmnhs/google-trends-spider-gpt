import os
import json
import time
from spider import get_article_content_simple
from upload_wp import post_wp, WP_PREFIX
from utils import generate_html_name
from rewrite import rewrite
from pathlib import Path

# 将指定URL内容上传到WordPress
def upload_wp_by_url(url):
    wp_url = ""
    # 抓取正文markdown
    real_title, content = get_article_content_simple(url)
    if content:
        # if len(content) < 5 * 1024:
        #     return ''
        os.makedirs(f"temp/origin/", exist_ok=True)
        os.makedirs(f"temp/agi/", exist_ok=True)

        # 保存到本地
        fpath = generate_html_name(url)
        article_fpath = f"temp/origin/{fpath}"
        with open(article_fpath, 'w', encoding="utf-8") as f:
            f.write(content)
        print(f"url={url}, path={article_fpath}")

        # 改写
        rewrite_fpath = f"temp/agi/{fpath}.md"
        rewrite_fpath = Path(rewrite_fpath)
        rewrite(article_fpath, rewrite_fpath)
        article_fpath = rewrite_fpath

        # # 上传到WordPress
        post_id = post_wp(real_title, article_fpath, url, "agi")
        if post_id != "":
            wp_url = f"{WP_PREFIX}{post_id}"
            print(f"success: {wp_url}")
    else:
       print(f"fail: {url}")

    return wp_url


if __name__ == "__main__":
    # upload_wp_by_url('https://worldtravelling.com/new-exhibition-to-look-out-for-this-is-new-york-100-years-of-the-city-in-art-and-pop-culture-opens-spring-2023/')
    upload_wp_by_url("https://standardnews.com/amazon-second-headquarters-locations/")
    # resp = []
    # urlMap = {}
    # with open('resp.json', 'r', encoding='utf-8') as f:
    #     resp_old = json.loads(f.read())
    #     for item in resp_old:
    #         if item['wp_url'] != "":
    #             urlMap[item['url']] = item['wp_url']
    # lines = []
    # with open('./article1.list', 'r', encoding='utf-8') as f:
    #     lines = f.readlines()
    # for line in lines:
    #     url = line.strip()
    #     if url in urlMap and urlMap[url] != "": # 直接采用之前的结果
    #         resp.append({"url": url, "wp_url": urlMap[url]})
            
    # for line in lines:
    #     url = line.strip()
    #     if url in urlMap and urlMap[url] != "":
    #         continue
    #     wp_url = upload_wp_by_url(url)
    #     resp.append({"url": url, "wp_url": wp_url})
    #     time.sleep(1)
    
    #     with open('resp.json', 'w', encoding='utf-8') as f:
    #         json.dump(resp, f, ensure_ascii=False, indent=2)
        
