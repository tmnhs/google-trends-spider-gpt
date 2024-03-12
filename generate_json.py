import json
import os
import sys
from utils import generate_html_name
from config import configs

#动态生成index.html文件
def generate_index_html():
    directory_path = configs.new_dir
    folders = [folder for folder in os.listdir(directory_path) if os.path.isdir(os.path.join(directory_path, folder))]
    with open(f"{directory_path}/index_tpl.html", "r", encoding="utf-8") as file:
        html_template = file.read()
    
    # 生成文件夹列表项
    folder_items = ""
    for folder in folders:
        folder_item = f'<li class="list-group-item"><a href="new_url.html?folder={folder}">{folder}</a></li>\n'
        folder_items += folder_item

    # 将文件夹列表项插入HTML模板
    html_content = html_template.format(folder_items=folder_items)

    # 将HTML内容保存到文件
    with open(f"{directory_path}/index.html", "w", encoding="utf-8") as file:
        file.write(html_content)


if __name__ == "__main__":
    generate_index_html()