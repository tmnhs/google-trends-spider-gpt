from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods.posts import NewPost,EditPost,GetPost
from wordpress_xmlrpc.methods.media import UploadFile
from wordpress_xmlrpc.methods import media
from bs4 import BeautifulSoup
import xmlrpc
import requests
import os
import re
import sys
import json
import mimetypes
import cairosvg
from PIL import Image
from googletrans import Translator
from io import BytesIO
from urllib.parse import urlsplit
from utils import generate_html_name
from urllib.parse import urlparse
from config import configs
import random

WP_URL = configs.wp_url
WP_PREFIX = configs.wp_prefix
WP_USERNAME = configs.wp_username
WP_PASSWORD = configs.wp_password

# 主入口
# 查询json文件获取文章标题、文章路径
# 上传到WordPress
# 将返回的文章ID写入json文件
def run(trend_date):
    process_trends_data(trend_date)

def process_trends_data(trend_date):
    origin_dir = configs.origin_dir
    new_dir = configs.new_dir

    # 加载指定日期的clean_data.json文件
    with open(f"{origin_dir}/{trend_date}/clean_data.json", "r", encoding="utf-8") as f:
        raw_data = f.read()
    data = json.loads(raw_data)

    # 解析JSON数据并生成新的数据结构
    trends_data = []
    for trend in data["default"]["trendingSearchesDays"][0]["trendingSearches"]:
        search_term = trend["title"]["query"]
        search_count = trend["formattedTraffic"]
        related_news = []
        for news in trend["articles"]:
            title = news["title"]
            url = news["url"]
            new_url = news.get("new_url", "")
            origin_url = news.get("origin_url", "")
            new_url = process_trends_article(title, url, trend_date, search_term, "agi", new_url)
            origin_url = process_trends_article(title, url, trend_date, search_term, "origin", origin_url)
            
            related_news.append({
                "title": title,
                "url": url,
                "origin_url": origin_url,
                "new_url": new_url
            })
            news["new_url"] = new_url
            news["origin_url"] = origin_url

        trends_data.append({
            "search_term": search_term,
            "search_count": search_count,
            "related_news": related_news
        })

    with open(f"{origin_dir}/{trend_date}/clean_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 保存新数据到google_dailytrends_new/{trend_date}/data.json
    os.makedirs(f"{new_dir}/{trend_date}", exist_ok=True)
    with open(f"{new_dir}/{trend_date}/data.json", "w", encoding="utf-8") as f:
        json.dump(trends_data, f, ensure_ascii=False, indent=2)

# 将trends文章上传WordPress获取url
def process_trends_article(title, url, trend_date, search_term, tag, wp_url):
    # if wp_url != "":
    #     return wp_url
    html_url_path = generate_html_name(url)
    article_fpath = f"{configs.origin_dir}{'' if tag == 'origin' else '_new'}/{trend_date}/{search_term}/{html_url_path}"
    post_id = post_wp(title, article_fpath, url, tag)
    if post_id != "":
        return f"{WP_PREFIX}{post_id}"
        
    return ""

# 获取图片url的文件名、后缀，示例：'aaa', '.jpg'
def extract_filename(url: str):
    match = re.search(r'([^/?&=]+)(\.(jpg|jpeg|png|webp|gif|svg))', url)
    if match:
        return match.group(1), match.group(2)
    return "img", ".jpg" #默认
  
# 将img_url上传到wp，返回wp图片url
def upload_image_to_wp(client, img_url):
    # 检查图片是否过小：文章目前直接过滤小图
    try:
        host = urlsplit(img_url).hostname
        response = requests.get(img_url, stream=True, timeout=3, headers={'User-Agent': configs.UA, 'Referer': f"https://{host}/"})
        response.raise_for_status()
        img_data = response.content
        response.close()
        with Image.open(BytesIO(img_data)) as img:
            # img = Image.open(BytesIO(img_data))
            width, height = img.size
            if width < 100 or height < 100:
                print(f"Image too small: {img_url}")
                return "",0
            if img.getextrema() == (0, 0) or img.getextrema() == (255, 255):
                print(f"Image is black or white: {img_url}")
                return "",0
    except Exception as e:
        print(f"Image process err: url={img_url} e={e}")
        return "",0
    
    # 上传wp
    img_name, img_ext = extract_filename(img_url)
    if "" == img_name:
        print(f"Image extract_filename fail: {img_url}")
        return "",0

    if img_ext == ".svg":
        img_data = cairosvg.svg2png(url=img_url)
        mime_type = "image/png"
        img_ext = ".png"
    else:
        mime_type = mimetypes.guess_type(img_url)[0]

    file_data = {
        "name": img_name + img_ext,
        "type": mime_type,
        "bits": xmlrpc.client.Binary(img_data)
    }
    resp_url = ""
    try:
        image_response = client.call(UploadFile(file_data))
        resp_url = image_response["url"]
        resp_id = image_response["id"]
    except Exception as e:
        print(f"client.call(UploadFile(file_data)) url={img_url} filed: {e}" )
        pass
    return resp_url,resp_id

def upload_video_to_wp(client, video_url, video_type):
    parsed_url = urlparse(video_url)
    filename = os.path.basename(parsed_url.path)
    if video_type == "": #根据video_url的扩展名来猜测
        ext = os.path.splitext(filename)[1].lower()
        if ext == ".mp4":
            video_type = "video/mp4"
        elif ext == ".webm":
            video_type = "video/webm"
        elif ext == ".ogg":
            video_type = "video/ogg"
        else:
            video_type = "video/mp4"
    host = urlsplit(video_url).hostname
    video_data = requests.get(video_url, headers={'User-Agent': configs.UA, 'Referer': f"https://{host}/"}).content
    file_data = {
        "name": filename,
        "type": video_type,
        "bits": video_data
    }
    video_response = client.call(UploadFile(file_data))
    return client.call(media.GetMediaItem(video_response['id'])).link

def translate(text, dest='en'):
    try:
        translator = Translator()
        result = translator.translate(text, dest)
        if result.text:
            return result.text
    except Exception as e:
        print(f"translate err: {e}")
    return text

# 将article_fpath上传到wp，指定title、category，url是源站点，返回post_id
def post_wp(title, article_fpath, url, category):
    print(f'url={url} path={article_fpath}')
    # 文章标题没有改写，但是可能会存在非英文的情况
    title = translate(title)

    # 读取文章内容
    article_content = ""
    if os.path.exists(article_fpath):
        with open(article_fpath, 'r', encoding="utf-8") as f:
            article_content = f.read()
    if article_content == "":
        return ""
    
    client = Client(WP_URL, WP_USERNAME, WP_PASSWORD)
    soup = BeautifulSoup(article_content, "html5lib")
    # 将img标签的src属性替换为WordPress的图片地址
    host = "https://" + urlsplit(url).hostname
    img_tags = soup.find_all("img")
    thumbnail_id=None
    for img_tag in img_tags:
        img_url = get_img_url(img_tag, host)
        if img_url:
            wp_img,wp_id = upload_image_to_wp(client, img_url)
            if thumbnail_id is None:
                thumbnail_id = wp_id
            if wp_img == "":
                img_tag.extract() # 删除这个img标签
            else:
                img_tag["src"] = wp_img
        else:
            img_tag.decompose()

    for video_tag in soup.find_all('video'):
        process_video_tag(client, video_tag, host)

    # 发布文章
    article_content = str(soup)
    post = WordPressPost()
    post.title = title
    post.content = article_content
    post.post_status = 'draft'
    # post.terms_names = {
    #     'category': [category]
    # }
    # 缩略图
    post.thumbnail = thumbnail_id
    # 随机取一个分类
    categorylist = ["popular", "trending", "recent"]
    category = random.choice(categorylist)
    post.terms_names = {
        'category': [category]
    }
    
    post_id = client.call(NewPost(post))
    print(f'Post published with ID {post_id}')
    return post_id

def process_video_tag(client, video_tag, host):
    video_tag['style'] = 'max-width: 100%; height: auto;'
    # <video src="video.mp4"></video>
    video_url, video_type = get_video_url(video_tag, host)
    if video_url != '':
        video_tag['src'] = upload_video_to_wp(client, video_url, video_type)
        return
    
    # 下面这种情况，我们仅保留MP4格式
    # <video>
    #     <source src="video.mp4" type="video/mp4">
    #     <source src="video.webm" type="video/webm">
    #     <source src="video.ogg" type="video/ogg">
    # </video>
    for source_tag in video_tag.find_all('source'):
        video_url, video_type = get_video_url(source_tag, host)
        if video_type != '' and video_type != 'video/mp4':
            source_tag.decompose()
            continue
        if video_url != "":
            source_tag['src'] = upload_video_to_wp(client, video_url, video_type)
    return

def get_video_url(tag, host):
    video_type = tag.get('type', '')
    src = tag.get('src', '')
    isBlob = False
    if src.startswith('blob:'): 
        isBlob = True
        src = src[5:]

    if src == "":
        tag.decompose()
        return "", ""
    if src.startswith('//'):
        video_url = "https:" + src
    elif src.startswith('/'):
        video_url = host + src
    else:
        video_url = src
    if isBlob:
        video_url = "blob:"+ video_url
    return video_url, video_type
    
# 根据img标签以及host获取图片url，并且删除非src的链接
def get_img_url(img_tag, host):
    #去除srcset属性
    img_tag["loading"] = "lazy"
    # attributes = ["srcset", "data-gl-src", "data-original", "data-src", "data-srcset", "data-original-mos", "data-pin-media", "data-normal", "src"]
    attributes = configs.img_field
    img_url = ""

    for attr in attributes:            
        value = img_tag.get(attr)
        if value is not None:
            first_url = value
            if " " in value:
                first_url = get_maxsize_img(value)
            if first_url.startswith("https://") or first_url.startswith("http://"):
                img_url = first_url
                break
            elif first_url.startswith("//"):
                img_url = "https:" + first_url
                break
            elif first_url.startswith("/"):
                img_url = host + first_url
                break
    # FIXME 
    # for attr in attributes:
    #     if attr != "src":
    #         del img_tag[attr]

    del img_tag["onload"]
    return img_url

def get_maxsize_img(srcset):
    urls = [url.strip() for url in srcset.split(',')]
    max_size = 0
    max_url = ''
    for url in urls:
        size = int(url.split()[-1][:-1])
        if size > max_size:
            max_size = size
            max_url = url.split()[0]
    return max_url

from urllib import parse
def upload_featured_image():
    lines = []
    
    with open('resp.json', 'r', encoding='utf-8') as f:
        resp_old = json.loads(f.read())
        for item in resp_old:
            if item['wp_url'] != "":
                lines.append(item['wp_url'])
    client = Client(WP_URL, WP_USERNAME, WP_PASSWORD)
    
    for url in lines:
        params  = parse.parse_qs( parse.urlparse( url ).query )
        post_id = int(params['p'][0])
        print(post_id)
        response = requests.get(url)
        html = response.text
        # 解析 HTML 页面内容，查找所有图片标签
        soup = BeautifulSoup(html, "html5lib")
        article = soup.find('div',{'class':'post-single-content'})
        if article:
            img_tags = article.find_all("img")
            thumbnail_url = None
            # 遍历所有图片标签，获取图片的 URL
            for img_tag in img_tags:
                img_url = img_tag.get("src")
                if img_url.startswith('https://passportspals.com/'):
                    thumbnail_url = img_url
                    break
            if thumbnail_url is None:
                continue
            _,wp_id = upload_image_to_wp(client, thumbnail_url)
            post = client.call(GetPost(post_id))
            print( post.thumbnail )
            post.thumbnail = wp_id
            client.call(EditPost(post_id,post))

if __name__ == "__main__":
    # 调用函数并传入trend_date参数  
    if len(sys.argv) != 2:
        print("Usage: python upload_wp.py date")
        trend_date = "20230617"
        #sys.exit(1)
    else:
        trend_date = sys.argv[1]

    run(trend_date)
    # upload_featured_image()


