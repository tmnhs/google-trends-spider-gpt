import requests
from goose3 import Goose
from goose3.configuration import Configuration, ArticleContextPattern
from bs4 import BeautifulSoup
import json
import os
import re
import random
import execjs
import hashlib
from urllib.parse import urlsplit, urlparse, urlunparse
from utils import generate_html_name, html_to_markdown
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.proxy import Proxy, ProxyType
import time
import nltk
from config import configs
nltk.download('punkt')

KNOWN_ARTICLE_CONTENT_PATTERNS=[]
for pattern in configs.goose_pattern:
    KNOWN_ARTICLE_CONTENT_PATTERNS.append(ArticleContextPattern(**pattern))

next_page_keywords = configs.page_turn.next
prev_page_keywords = configs.page_turn.prev

# get_top_html_raw
content_tags = []
for pattern in configs.goose_pattern:
    if pattern.get('attr') is not None and pattern['attr']=='class':
        content_tags.append('.'+pattern['value'])

# selemium爬虫+重试
def get_html_by_selenium_retry(url):
    retries = 0
    delay = 10
    max_retries = 5
    while retries < max_retries:
        try:
            html, isScroll = get_html_by_selenium(url)
            return html, isScroll
        except Exception as e:
            retries += 1
            time.sleep(delay+retries*2)
            print(f"get_html_by_selenium_retry url={url} e={e}")

# 利用selemium爬取滚动下拉分页，最后返回总的html
def get_html_by_selenium(url):
    print(f"get_html_by_selenium url={url}")
    isScroll = False
    # 创建一个Chrome浏览器实例
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # 启动无头模式
    options.add_argument("--disable-gpu")  # 禁用GPU加速
    options.add_argument('--disable-extensions')
    options.add_argument('--ignore-certificate-errors')
    options.add_argument(f"--remote-debugging-address={configs.webdriver.debugging_addr}")
    options.add_argument(f"--remote-debugging-port={configs.webdriver.debugging_port}")
    options.add_argument(f"--user-agent={configs.UA}")
    driver = webdriver.Remote(
        command_executor=configs.webdriver.command_executor,
        options=options
    )
    driver.set_window_size(1440, 900)
    # 访问页面并抓取数据
    driver.get(url)
    time.sleep(10)
    url = driver.current_url
    actions = ActionChains(driver)
    
    # 滑动触发分页、动态加载
    while True:
        rand_num = random.randint(100, 1000)
        last_height = driver.execute_script("return document.body.scrollHeight")
        # 执行JavaScript脚本模拟鼠标滚动
        driver.execute_script("window.scrollBy(0,{0})".format(1000+rand_num))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        actions.send_keys(Keys.PAGE_DOWN).perform()
        actions.click_and_hold().move_by_offset(0, 100).release().perform()

        # 等待页面加载
        time.sleep(5+rand_num/1000.0)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if url != driver.current_url:
            isScroll = True

        # 获取当前页内容
        if new_height == last_height:
            break
    
    html = driver.page_source
    # 关闭浏览器
    driver.quit()
    return html, isScroll

def get_html_by_goose_false_url(url):
    threshold = 5 
    try:
        parsed_url = urlparse(url)
        rand_num = random.randint(1000, 10000)
        new_path = parsed_url.path.rstrip('/') + f'/{rand_num}'
        new_url = urlunparse((parsed_url.scheme, parsed_url.netloc, new_path, parsed_url.params, parsed_url.query, parsed_url.fragment))
        title, html, _, _, _ = get_html_by_goose(new_url)
        if check_html_has_many_page(html):
            return title, html
    except Exception as e:
        pass
    
    return '', ''

def check_html_has_many_page(html):
    threshold = 5
    soup = BeautifulSoup(html, 'html5lib')
        
    # 检查<article>标签
    if len(soup.find_all('article')) > threshold:
        return True
        
    # 检查class名称
    class_list = ['article', 'invisibleBorder', 'after-image-content', 'firstImage', 'omg-onepager-section']
    for class_name in class_list:
        elements = soup.find_all(class_=class_name)
        if len(elements) > threshold:
            return True    
        
    # 检查以total-paragraphs-, section- 或 page- 开头的class名称
    class_regex = re.compile(r'^(total-paragraphs-|page-|section-)')
    elements = soup.find_all(class_=class_regex)
    if len(elements) > threshold:
        return True
        
    # 检查id以section-或page-开头的元素
    elements = soup.find_all(lambda tag: tag.has_attr('id') and (tag['id'].startswith('section-') or tag['id'].startswith('page-')))
    if len(elements) > threshold:
        return True
    return False

# 动态页面爬虫: 返回title、html、next_url
def dynamic_spider(url):
    raw_html, isScroll = get_html_by_selenium_retry(url)
    if raw_html == "":
        return "", "", ""
    
    # goose解析必须先去除<p></p>，否则会重复, 后面看看是否放到goose步骤
    soup = BeautifulSoup(raw_html, 'html5lib')
    for el in soup.find_all(['p', 'div', 'li']):
        if not el.contents and not el.find_all():
            el.decompose()
    raw_html = str(soup)

    # 解析网页
    title, html, next_url, top_image, no_circle = get_html_by_goose(url, raw_html)
    return title, html, next_url

# 使用goose爬虫
def get_html_by_goose(url, raw_html=''):
    no_circle = False 
    config = Configuration()
    config.http_timeout = 10
    config.browser_user_agent = configs.UA
    host = urlsplit(url).hostname
    config.http_headers = {
        "Referer": f"https://{host}/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    }
    config.known_context_patterns= KNOWN_ARTICLE_CONTENT_PATTERNS
    # goose解析
    try:
        g = Goose(config)
        if raw_html != '': # 指定了html则不用url抓取
            article = g.extract(raw_html=raw_html)
        else:
            article = g.extract(url=url)
            raw_html = article.raw_html
        title = article.title
        html = article.top_node_raw_html
        top_image = article.top_image
    except Exception as e:
        print(f"get_html_by_goose goose fail, url={url}, e={e}")
    
    if raw_html is None or raw_html == '':
        return '', '', '', '', False
    # 如果没有图，我们就塞一个
    if top_image is None or top_image == '':
        top_image, html = generate_img(article, html)
    if top_image is None or top_image == '':
        html = get_top_html_raw(raw_html)
        top_image, html = generate_img(article, html)
    g.close()
    # response = requests.get(url)
    # title = ''
    # raw_html = response.text
    # 解析next_url    
    next_url = get_nexturl_by_html(raw_html, url)
    if html is None:
        html = ""
    # print(12)
    # 存在一种特殊网页，js中保存了所有数据，不用翻页
    # todo
    # js_html, js_img = get_var_from_js(raw_html)
    # if js_html != '' and js_img != '':
    #     html = js_html
    #     top_image = js_img
    #     no_circle = True
    #     next_url = ""
    # print(123)
    return title, html, next_url, top_image, no_circle

def get_var_from_js(raw_html):
    html = ''
    top_img = ''
    soup = BeautifulSoup(raw_html, 'html5lib')
    # 1. post字符串
    post_map = [
        {
            'id': 'core-app-app-js-extra',
            'js_code': """
                var post = "";
                function extractVarPost(scriptText) {
                    eval(scriptText);
                    return post;
                }"""
        },
        {
            'id': 'core-app-app-js-after',
            'js_code': """
                var post = {};
                function extractVarPost(scriptText) {
                    eval(scriptText);
                    return JSON.stringify(post);
                }"""
        }
    ]
    for item in post_map:
        script_tag = soup.find('script', {'id': item['id']})
        js_env = execjs.compile(item['js_code'])
        if script_tag:
            if script_tag.text != "":
                var_post = js_env.call("extractVarPost", script_tag.text)
            else:
                var_post = js_env.call("extractVarPost", script_tag.string)
            if var_post:
                if isinstance(var_post, str):
                    var_post = json.loads(var_post)
                if 'featured_image' not in var_post:
                    continue
                top_img = var_post['featured_image']
                pages = []
                pages.append(var_post['start_page'])
                pages.extend(var_post['slides'])
                for page in pages:
                    for item in page:
                        if 'image' in item['type']:
                            url = item['fields']["image"]
                            html += f'<img src="{url}">'
                        elif 'content' in item['type']:
                            text = item['fields']['content'].strip()
                            html += f'{text}'
                        elif 'title' in item['type']:
                            text = item['fields']['title'].strip()
                            html += f'<h2>{text}</h2>'
                break
            
    if html != '' and top_img != '':
        return html, top_img
    
    scripts = soup.find_all('script')
    js_code = """
        var omg_ads = "";
        function extractVarPost(scriptText) {
            eval(scriptText);
            return omg_ads;
        }
    """
    js_env = execjs.compile(js_code)
    for script in scripts:
        try:
            if script.text != "":
                var_post = js_env.call("extractVarPost", script.text)
            else:
                var_post = js_env.call("extractVarPost", script.string)
            if var_post:
                html = ''.join(var_post['content'])
                soup2 = BeautifulSoup(html, 'html5lib')
                top_img = soup2.find('img').get('src', '')
                break
        except Exception as e:
            pass
    if html != '' and top_img != '':
        return html, top_img
    
    return html, top_img
    
# goose没有获取到top_img时，自己尝试生成一个
def generate_img(article, html):
    if html is None or html == '':
        return '', ''
    # html中存在图片，直接返回html
    soup = BeautifulSoup(html, 'html5lib')
    img_in_html = soup.find_all('img')
    for img in img_in_html:
        for fld in configs.img_field:
            img_url = img.get(fld, '')
            if img_url != '':
                return img_url, html

    # html塞入一张图片
    if 'opengraph' in article.infos and 'image' in article.infos['opengraph'] and article.infos['opengraph']['image'] != "":
        top_images = article.infos['opengraph']['image']
        if len(img_in_html) > 0:
            img_url = top_images[0]
            img_tag = f'<img src="{img_url}"/>'
            html = f"{img_tag}\n{html}"
            return img_url, html
    
    return '', html

# 在html中查找下一页链接: 按照a标签文字查找
def get_nexturl_by_html(html, url):
    next_url = ""
    soup = BeautifulSoup(html, 'html5lib')
    next_page_links = [tag for tag in soup.find_all('a') if ''.join(tag.stripped_strings).lower() in next_page_keywords]
    if next_page_links is not None and len(next_page_links) > 0:
        next_url = next_page_links[0].get('href', '')
    if next_url.startswith('//'):
        next_url = f"http:{next_url}"
    elif next_url.startswith('/'):
        host = urlsplit(url).hostname
        next_url = f"http://{host}{next_url}"
    return next_url

# 无限循环页面，此时只翻固定页数，并且根据两次内容是否相同进行去重
def get_html_by_goose_circle(base_url):
    if not base_url.endswith('/'):
        base_url = f"{base_url}/"
    title, html, _, _, _ = get_html_by_goose(base_url, '')
    text = html_to_markdown(html)
    md5_hash = hashlib.md5(text.encode('utf-8')).hexdigest()

    md5_cnt = {}
    md5_cnt[md5_hash] = 1
    # FIXME 
    for i in range(1, 150): # 最多翻200页
        url = f"{base_url}{i}"
        max_retries = 3
        retries = 0
        while retries < max_retries:
            try: # 错过某一页直接跳过
                _, html_next, _, _, _ = get_html_by_goose(url, '')
                break
            except Exception as e:
                print(f'get_html_by_goose_circle url={url}, e={e}')
                continue
        text_next = html_to_markdown(html_next)
        md5_hash = hashlib.md5(text_next.encode('utf-8')).hexdigest()
        if md5_hash not in md5_cnt:
            md5_cnt[md5_hash] = 1
            print(url, flush=True)
            html += html_next
            text = text_next
        else:
            md5_cnt[md5_hash] += 1
            if md5_cnt[md5_hash] >= 5:
                break

    return title, html

# 点击分页、滚动分页的爬虫可以用这个函数
def get_html_multy(url):
    # 0. go.reference.com 站点是无限循环，且不可一次性抓取
    print(11)
    
    if 'go.reference.com' in url or 'rfvtgb' in url:
        return get_html_by_goose_circle(url)
    
    if 'diy' in url:
        title, html, next_url = dynamic_spider(url)
        return title, html 
    # 1. 先试探是否可以通过构造URL直接获取： uri/10000
    print(111)
    
    title, html = get_html_by_goose_false_url(url)
    if html != "" and title != "":
        return title, html
    print(1111)
    
    # 2. 通过goose库试探是否可静态抓取
    title, html, next_url, top_img, no_circle = get_html_by_goose(url, '')
    print(1)
    # 点击分页且有图，不需要selemium，但是需要循环
    if (next_url != "" and top_img is not None) or no_circle: 
        print(2)
        while next_url != "":
            time.sleep(2) # 频繁
            print(next_url, flush=True)
            _, html_next, next_url, _, _ = get_html_by_goose(next_url)
            html += html_next

    else: # 滚动分页、动态加载，需要selemium
        # 上面试探不行，最后再用selemium
        print(3)
        title, html, next_url = dynamic_spider(url)
        while next_url != "" and html != "":
            print(next_url, flush=True)
            _, html_next, next_url = dynamic_spider(next_url)
            html += html_next

    return title, html

# 尽量不走这个函数
def get_top_html_raw(html):
    soup = BeautifulSoup(html, 'html5lib')
    main_tags = ["article", "section.main", "section.articleBody", "main"]
    main = None
    for tag in main_tags:
        main = soup.select_one(tag)
        if main is not None:
            break
    if main is None:
        main = soup
    
    # content_tags = [".single", ".td-post-content", ".content-wrapper", ".content-area", ".post-area__content-wrapper", ".post-content-container", ".content", ".entry-content", ".sde-single-post__content", ".post-page", ".page-content", ".post-content", ".content-main", ".article-body", ".article-content", ".article", ".article__body", ".article__content", ".ar"]
    content = None
    for tag in content_tags:
        content = main.select_one(tag)
        if content is not None:
            break
    if content is None:
        content = main

    return str(content)


# 爬取url正文并返回内容
def get_article_content_simple(url):
    # if 'rfvtgb' in url:
    #     return '', ''
    delet_tags = set()
    try:
        # if 'www.wackojaco.com' in url:
        title, html, _, _, _ = get_html_by_goose(url) # 单页类型的文章
        # else:
        #     title, html = get_html_multy(url) # 多页类型的文章
        if html == '' or title == '':
            return '', ''
        print(title,html   )
        soup = BeautifulSoup(html, "html5lib")
        unwanted_elements = []
        for tag in soup.find_all(True):
            if tag.name not in configs.allow_tag:
                delet_tags.add(tag.name)
                unwanted_elements.append(tag)

        # class黑名单
        unwanted_elements.extend(soup.find_all(class_=lambda x: x is not None and any(item in x.split() for item in configs.unwanted_class)))
        # 正则
        for unwanted_re in configs.unwanted_re_class:
            unwanted_elements.extend(soup.find_all(class_=re.compile(r''+unwanted_re))) 
        
        # 特定url的class、id黑名单
        for url_unwanted in configs.url_unwanted_re:
            if url_unwanted['url'] in url:
                print(url)
                if url_unwanted.get('unwanted_re_class') is not None:
                    for re_class in url_unwanted['unwanted_re_class']:
                        print("unwanted_class:",re_class)
                        unwanted_elements.extend(soup.find_all(class_=re.compile(r'' + re_class)))
                if url_unwanted.get('unwanted_re_id') is not None:
                    for re_id in url_unwanted['unwanted_re_id']:
                        print("unwanted_id:",re_id)
                        unwanted_elements.extend(soup.find_all(id=re.compile(r'' + re_id)))
                        
        for link in soup.find_all('a'):
            if link.string is not None:
                link_str = link.string.lower()
                for prefix in configs.readmore_prefix:
                    if link_str.startswith(prefix):
                        unwanted_elements.append(link)
                        break
                
        for tag in unwanted_elements:
            tag.decompose()

        # PM要求删除链接，但是保存Twitter、Facebook、Instagram的分享卡片
        for link in soup.find_all('a'):
            href = link.get("href", '')
            is_social_link = False
            for prefix in configs.social_link_prefix:
                if href.startswith(prefix):
                    is_social_link = True
                    break
            if not is_social_link:
                link.unwrap()
        
        # picture标签下仅需要img，并且img的src以http开头
        for picture_element in soup.find_all('picture'):
            img_element = picture_element.find('img')
            source_elements = picture_element.find_all('source')
            img_src = img_element.get('src', '')
            source_img = ""
            if source_elements:
                source_img = source_elements[0].get('srcset', '')
            if not img_element: # 如果没有img标签
                img_element = soup.new_tag('img', src=source_img, alt='')
                picture_element.insert(0, img_element)
            elif img_element and not img_src.startswith('http'):
                img_element['src'] = source_img
            for tag in picture_element.find_all():
                if tag != img_element:
                    tag.unwrap()
        # span标签在wp上会被格式化为p
        for span in soup.find_all(['span', 'p'], {'data-offset-key': True}):
            span.unwrap()

        # 判断元素是否为空，或者广告标记
        for el in soup.find_all(['p', 'div', 'li', 'span']):
            if not el.contents and not el.find_all():
                el.decompose()
            elif el.text.lower().strip() in configs.ad_string:
                el.decompose()
            elif el.text.lower().strip() in next_page_keywords or el.text.lower().strip() in prev_page_keywords:
                el.decompose()
        #没有alt属性的图片在改写之后可能会被删除，手动添加
        for img in soup.find_all('img'):
            alt = img.get('alt','')
            if alt == '':
                img['alt']='img'
            data_lazy_src=img.get('data-lazy-src','')
            if data_lazy_src !='':
                img['src']=data_lazy_src
                img['data-lazy-src']=''
                
        
        # 去除padding样式
        for tag in soup.find_all(style=re.compile(r'padding-(top|bottom)\s*:\s*[^;]*;')):
            style = tag.get('style')
            new_style = re.sub(r'padding-(top|bottom)\s*:\s*[^;]*;', '', style)
            tag['style'] = new_style

        print(delet_tags)
        soup = insert_script(soup)
        # 删除某些属性
        for tag in soup.find_all(True):
            for attr in configs.del_field:
                del tag[attr]

        final_html = str(soup)
        # 连续hr删除
        pattern = re.compile(r'<hr\s*/?>\s*(?:<br\s*/?>\s*)*<hr\s*/?>', re.IGNORECASE)
        final_html = pattern.sub('', final_html)
        return title, final_html
    except Exception as e:
        print(f"{url} failed with error: {e}")
        return "", ""

"""
在WordPress的Functions.php中有相应短代码：
// Twitter
function my_twitter_script_shortcode() {
    return '<script async src="https://platform.twitter.com/widgets.js" charset="utf-8"></script>';
}
add_shortcode('my_twitter_script', 'my_twitter_script_shortcode');

// Facebook
function my_facebook_script_shortcode() {
    return '<script async defer crossorigin="anonymous" src="https://connect.facebook.net/en_US/sdk.js#xfbml=1&version=v12.0"></script>';
}
add_shortcode('my_facebook_script', 'my_facebook_script_shortcode');

// Instagram
function my_instagram_script_shortcode() {
    return '<script async src="https://www.instagram.com/embed.js"></script>';
}
add_shortcode('my_instagram_script', 'my_instagram_script_shortcode');

// YouTube
function my_youtube_script_shortcode() {
    return '<script src="https://www.youtube.com/iframe_api"></script>';
}
add_shortcode('my_youtube_script', 'my_youtube_script_shortcode');

// LinkedIn
function my_linkedin_script_shortcode() {
    return '<script src="https://platform.linkedin.com/in.js" type="text/javascript">lang: en_US</script>';
}
add_shortcode('my_linkedin_script', 'my_linkedin_script_shortcode');
"""
def insert_script(soup):
    # 检查是否包含Twitter分享卡片
    if soup.find_all("blockquote", class_="twitter-tweet"):
        soup.body.insert(0, "[my_twitter_script]")

    # 检查是否包含Facebook分享卡片
    if soup.find_all("div", class_=["fb-post", "fb-video"]):
        soup.body.insert(0, "[my_facebook_script]")

    # 检查是否包含Instagram分享卡片
    if soup.find_all("blockquote", class_="instagram-media"):
        soup.body.insert(0, "[my_instagram_script]")

    if soup.find_all("iframe", src=lambda x: x and "youtube.com/embed" in x):
        soup.body.insert(0, "[my_youtube_script]")
    if soup.find_all("iframe", src=lambda x: x and "linkedin.com/embed" in x):
        soup.body.insert(0, "[my_linkedin_script]")
    return soup

def ingest_trends():
    # Request Google Trends API
    data = ""
    try:
        response = requests.get(configs.google_api_url, timeout=10)
        data = response.text
    except requests.exceptions.Timeout:
        print(configs.google_api_url + " timedout")
        return
    
    print(configs.google_trend_white_switch)
    # Remove the unwanted header from the JSON data
    clean_data = data.replace(")]}',", "", 1)
    # with open('./google_dailytrends/20230617/clean_data.json', 'r', encoding='utf-8') as f:
    #     clean_data = f.read()

    # Parse JSON data
    trends_data = json.loads(clean_data)
    
    base_dir = configs.origin_dir
    
    # Extract trend titles and article URLs
    trend_date = trends_data['default']['trendingSearchesDays'][0]['date']
    trends = trends_data['default']['trendingSearchesDays'][0]['trendingSearches']
    for trend in trends:
        title = trend['title']['query']
        articles = trend['articles']
        # Get content of each article URL and save to local files
        for article in articles:
            url = article['url']
            article_title = article['title']
            whether_crawl = False
            # 开启白名单
            if configs.google_trend_white_switch:
                for url_prefix in configs.google_trend_white_list:
                    # 判断是否在白名单
                    if url.startswith(url_prefix.strip()):
                        whether_crawl = True
                        break
            else:
                whether_crawl = True
            if whether_crawl:
                real_title, content = get_article_content_simple(url)
                if content:
                    if content=='<html><body></body></html>':
                        continue
                    # Create directory for the search keyword if it doesn't exist
                    os.makedirs(f"{base_dir}/{trend_date}/{title}", exist_ok=True)

                    # Save article content to a local file
                    file_name = generate_html_name(url)
                    file_path = f"{base_dir}/{trend_date}/{title}/{file_name}"
                    # print(file_path)
                    with open(file_path, "w", encoding="utf-8") as file:
                        file.write(content)
                    if real_title != article_title and "" != real_title.strip():
                        article['title'] = real_title
                else:
                    print(f"Article content not found for {url}")

    # save json data
    os.makedirs(f"{base_dir}/{trend_date}", exist_ok=True)
    with open(f"{base_dir}/{trend_date}/clean_data.json", "w", encoding="utf-8") as file:
        json.dump(trends_data, file, indent=2)

if __name__ == "__main__":
    ingest_trends()
