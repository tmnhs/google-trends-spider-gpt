# 前言

爬取Google Trends（谷歌热点）或者指定url的文章，使用chatgpt改写，并上传到WordPress保存

# 1. 爬虫
* 调用Google Trends API，结果json保存到 google_dailytrends/{trend_date}/clean_data.json ，其中文章标题如果被截断..., 在爬虫时进行纠正, 并写入keywords、summary信息
* 通过json获取相关文章URL后，爬虫提取标签p、h1、h2等，正文写入本地磁盘 google_dailytrends/{trend_date}/{query_title}/{URL拼接}.html，html中图片标签做了处理

```
python spider.py
```

# 2. 改写
* 先利用langchain的spliter进行分段，重合度为0
* 通过clean_data.json获取标题，将标题、snippet、keywords、summary，一起用gpt优化标题，该逻辑目前关了
* 分段改写：加了重试机制、重试前sleep 120，并且总失败次数达到10次就直接退出脚本，改写后拼接到 google_dailytrends_new 目录下

```
python rewrite.py 20230607
```

# 3. 上传WordPress
* 将google_dailytrends/{trend_date}、google_dailytrends_new/{trend_date}目录下的文件都上传到wp，里面的图片也爬下来
* 生成 google_dailytrends_new/{trend_date}/data.json ，其中origin_url, new_url分别对应源文章、改写文章在wp上的URL
```
python upload_wp.py 20230613
```

# 4. 呈现
生成index.html：需要判断有哪些日期文件夹

```
python generate_json.py 20230607
```

在Nginx上配置了路由规则

# 5. 直接将指定URL上传WordPress
修改url_to_wp.py中的url参数
```
python url_to_wp.py
```