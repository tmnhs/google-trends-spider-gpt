from dynaconf import Dynaconf

configs = Dynaconf(
    settings_files=['./conf/spider/article_common.yml',         \
                    './conf/spider/article_google_trends.yml',  \
                    './conf/spider/article_goose_pattern.yml',  \
                    './conf/spider/article_unwanted_class.yml', \
                    './conf/spider/article_personalized_url.yml',\
                    './conf/global.yml',                        \
                    './conf/openai.yml',                        \
                    './conf/wordpress.yml',                     \
                    ],
)