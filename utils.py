import html2text
import markdown

# Function to generate a file name based on a given URL
def generate_file_name(url):
    file_name = url.split("//")[-1]
    file_name = file_name.replace("/", "_")
    return f"{file_name}.txt"

#爬虫文件以.txt结尾，但是最终展示时采用.html文件
def generate_html_name(url):
    file_name = url.split("//")[-1]
    file_name = file_name.replace("/", "_")
    file_name = file_name[:250]
    return f"{file_name}.html"

def html_to_markdown(html):
    h = html2text.HTML2Text()
    h.body_width = 0  # 禁用文本截断
    h.ignore_links = True
    h.ignore_images = False
    return h.handle(html)

def markdown_to_html(md):
    html = markdown.markdown(md)
    return html

def read_file_to_list(file_path):
    """
    读取一个文件中的内容到一个字符串list中
    :param file_path: 文件路径
    :return: 包含文件内容的字符串list
    """
    # 打开文件并读取内容
    with open(file_path, 'r') as f:
        content = f.read()

    # 将内容按行分割成字符串list
    value_list = content.split('\n')

    # 去除空行和空格
    value_list = [value.strip() for value in value_list if value.strip()]

    return value_list
