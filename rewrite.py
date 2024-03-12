import os
import io
import sys
import time
import re
from pathlib import Path
from langchain.text_splitter import NLTKTextSplitter
from langchain.text_splitter import (
    RecursiveCharacterTextSplitter,
    Language,
)
from langchain.chat_models import AzureChatOpenAI
from langchain.schema import HumanMessage
from langchain.schema import SystemMessage
from utils import generate_html_name, html_to_markdown, markdown_to_html
from config import configs

import logging
# 配置日志级别、格式和输出
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S',
                    filename='my_log.log')  # 将日志输出到文件 "my_log.log"

# 获取一个名为 "my_logger" 的 logger 实例
logger = logging.getLogger("my_logger")

# 设置OpenAI API密钥
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


#gpt-3.5-turbo
BASE_URL = configs.base_url
API_KEY = configs.api_key
DEPLOYMENT_NAME = configs.deployment_name
MODEL = configs.model
OPENAI_VERSION = configs.openai_version

PROMPT_PARAGRAPH = configs.prompt_paragraph
PROMPT_TITLE = configs.prompt_title

def rewrite_paragraph(paragraph, prompt_type):
    if len(paragraph.strip()) == 0:
        return ""

    time.sleep(15)
    model = AzureChatOpenAI(
        openai_api_base=BASE_URL,
        openai_api_version=OPENAI_VERSION,
        model=MODEL,
        max_tokens=2000,
        temperature=0,
        deployment_name=DEPLOYMENT_NAME,
        openai_api_key=API_KEY,
        openai_api_type="azure"
    )
    response = model([
        SystemMessage(content=prompt_type), HumanMessage(content=paragraph)
    ])
    return response.content

total_fail = 0
def rewrite_paragraph_withsleep(paragraph, prompt_type):
    retries = 0
    delay = 120
    max_retries = 2
    while retries < max_retries:
        try:
            result = rewrite_paragraph(paragraph, prompt_type)
            return result
        except Exception as e:
            global total_fail
            total_fail += 1
            if total_fail > 10:
                exit(10)
            retries += 1
            print(f"exec rewrite_paragraph exception: {e}. retrying {retries}... paragraph {paragraph}", flush=True)
            time.sleep(delay)
    
img_pattern = r"!\[.*\]\(.*\)"

def rewrite(filepath, newfilepath):
    # 判断是否已经改写过
    # if newfilepath.exists():
    #     return
    # 读取原始文件，将段落存入列表
    with open(filepath, 'r', encoding="utf-8") as file:
        state_of_the_union = file.read()
    state_of_the_union = html_to_markdown(state_of_the_union)
    text_splitter = RecursiveCharacterTextSplitter.from_language(language=Language.MARKDOWN, chunk_size=1000, chunk_overlap=0)
    new_paragraph = text_splitter.create_documents([state_of_the_union])
    print(len(new_paragraph), flush=True)

    # 改写每个段落
    rewritten_paragraphs = []
    for paragraph in new_paragraph:
        # print('new paragraph:',paragraph)
        new_include_img = re.findall(img_pattern,paragraph.page_content)
        resp = rewrite_paragraph_withsleep(paragraph.page_content, PROMPT_PARAGRAPH)
        if "No change needed" in resp:
            resp = paragraph.page_content
        if resp.startswith("* "): #列表第一项前面无空格导致格式有问题，先这样解决
            resp = '  ' + resp
        # print('resp:',resp)
        rewrite_include_img = re.findall(img_pattern,resp)
        #如果原段落有图片而改写之后的段落没有，则在改写段落最后添加
        if len(new_include_img)>len(rewrite_include_img):
            for new_img in new_include_img:
                exist = False
                for rewrite_img in rewrite_include_img:
                    if new_img == rewrite_img:
                        exist = True
                        break
                if not exist:
                    resp=resp + '\n' + new_img
        rewritten_paragraphs.append(resp)
        

    # 将改写后的段落拼接成新的文章
    new_article = '\n'.join(rewritten_paragraphs)
    new_article = markdown_to_html(new_article)
    # 将新文章写入输出文件
    with open(newfilepath, 'w', encoding="utf-8") as file:
        file.write(new_article)
        print(newfilepath)


def process_largest_files(trend_date: str):
    base_dir = f"{configs.origin_dir}/{trend_date}"
    base_dir_new = f"{configs.new_dir}/{trend_date}"

    if not os.path.exists(base_dir):
        print(f"No data found for trend date: {trend_date}")
        return

    for query_title_dir in os.scandir(base_dir):
        if query_title_dir.is_dir():
            largest_article_file = None
            largest_article_size = 0

            # if "Fed meeting" != query_title_dir.name and "Eminem" != query_title_dir.name:  # debug
            #     continue
            for article_file in os.scandir(query_title_dir.path):
                # if article_file.is_file() and article_file.name.endswith(".html"):
                #     if article_file.stat().st_size > largest_article_size:
                #         largest_article_size = article_file.stat().st_size
                #         largest_article_file = article_file

                # if largest_article_file:
                largest_article_file = article_file
                new_dir = Path(base_dir_new) / query_title_dir.name
                new_dir.mkdir(parents=True, exist_ok=True)

                new_file_path = new_dir / largest_article_file.name
                print(largest_article_file.path, flush=True)
                rewrite(largest_article_file.path, new_file_path)
            else:
                print(f"No article files found in: {query_title_dir.path}")


def run(trend_date: str):
    # 处理最大的文件
    process_largest_files(trend_date)
    # rewrite('google_dailytrends/20230614/White House press secretary/economictimes.indiatimes.com_news_international_us_white-house-reveals-press-secretary-karine-jean-pierre-violated-hatch-act-heres-what-it-means_articleshow_100993357.cms.md', 
    #         Path('google_dailytrends_new/20230614/White House press secretary/economictimes.indiatimes.com_news_international_us_white-house-reveals-press-secretary-karine-jean-pierre-violated-hatch-act-heres-what-it-means_articleshow_100993357.cms.md'))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python rewrite.py date")
        trend_date = "20230614"
        # sys.exit(1)
    else:
        trend_date = sys.argv[1]
    run(trend_date)
