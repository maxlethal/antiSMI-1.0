import numpy as np
import pandas as pd

import re
from datetime import datetime, timedelta
import sqlalchemy

from sklearn.cluster import AgglomerativeClustering
from navec import Navec

"""
Превращение слов в эмбеддинги осуществляется c помощью navec (часть NLP-проекта natasha, 250 000 слов, эмб длиной 300), 
обученными на новостном корпусе русскоязычных текстов. Это Glove-эмбеддинги, уменьшенные с помощью квантизации.
Navec покрывает 98% слов в новостных статьях, проблема OOV решается с помощью спецэмбеддинга <unk>.
Эмбеддинг предложений - среднее эмбеддингов его слов, что хорошо работает для кластеризации.
"""
path = 'models//navec.tar'
navec = Navec.load(path)

parse_time_dict = \
	{1: {'start': '21:00:00', 'finish': '06:59:59'},
	 2: {'start': '07:00:00', 'finish': '11:59:59'},
	 3: {'start': '12:00:00', 'finish': '16:59:59'},
	 4: {'start': '17:00:00', 'finish': '20:59:59'}}

engine = sqlalchemy.create_engine('sqlite:///db.db')

pd.set_option('max_colwidth', 120)
pd.set_option('display.width', 500)
pd.set_option('mode.chained_assignment', None)


def get_clean_word(word: str) -> str:
	"""Очистка слов от лишних символов, приведение к требованиям библиотеки navec"""
	word = re.sub('[^a-zа-яё-]', '', word, flags=re.IGNORECASE)
	word = word.strip('-')
	return word


def news2emb(news: str) -> np.ndarray:
	"""Предложение --> эмбеддинг предложения"""
	news_clean = [get_clean_word(word) for word in news.split()]
	embeddings_list = []
	for word in news_clean:
		try:
			embeddings_list.append(navec[word.lower()])
		except KeyError:  # если OOV, эмбеддинг = спецэмбедингу "unknown" для natasha
			embeddings_list.append(navec['<unk>'])
	news_emb = np.mean(embeddings_list, axis=0)
	return news_emb


def date_news(parse_date=str(datetime.now().date()), part_number=0):
	"""новости на дату в формате YYYY-MM-DD -> dataframe, short_news_list, embeddings"""
	# Для утренней подборки стартовая дата должна быть вчерашней
	if part_number != 1:
		start_parse_date = parse_date
	else:
		start_parse_date = str((datetime.strptime(parse_date, '%Y-%m-%d') - timedelta(days=1)).date())
	if part_number != 0:
		start_parse_time = parse_time_dict[part_number]['start']
		finish_parse_time = parse_time_dict[part_number]['finish']
		start_time = start_parse_date + ' ' + start_parse_time
		finish_time = parse_date + ' ' + finish_parse_time
	else:
		start_time = start_parse_date + ' ' + '00:00:00'
		finish_time = parse_date + ' ' + '23:59:59'
	news_df = pd.read_sql(f"SELECT * FROM news WHERE news.date BETWEEN '{start_time}' AND '{finish_time}'", engine)
	list_news = news_df.title.to_list()
	embeddings = [news2emb(news) for news in list_news]
	return news_df, list_news, embeddings


def show_date(parse_date=str(datetime.now().date()), part_number=0) -> pd.DataFrame:
	"""
	Группировка новостей алгоритмом агломеративной кластеризации: labels (получаем через дату и период) -> pandas.df
	Для просмотра кластера в функцию нужно передать дату в формате YYYY-MM-DD и, при необходимости, временной интервал
	Если не передавать параметры в функцию, будет осуществляться кластеризация новостей за последние сутки
	Можно задать обработку 4-х промежутков в течение суток (задаются ключами словаря parse_time_dict 1-4)
	или обрабатывать сразу все сутки (0, парсится по умолчанию)
	"""
	date_df, day_news_list, embeddings = date_news(parse_date, part_number)
	# Если новости за ночь не появились и новостной датафрейм оказался пустым - отдаём новости прошедшего дня
	if date_df.empty:
		parse_date = str((datetime.strptime(parse_date, '%Y-%m-%d') - timedelta(days=1)).date())
		date_df, day_news_list, embeddings = date_news(parse_date)

	clast_model = AgglomerativeClustering(n_clusters=None, affinity='cosine', linkage='complete',
	                                      distance_threshold=0.3)
	labels = clast_model.fit_predict(list(embeddings))
	date_df['label'] = labels
	date_df['count'] = date_df.groupby('label')['label'].transform('count')
	date_df = date_df.sort_values(by=['count', 'label'], ascending=[False, True])
	date_df.drop('count', axis=1, inplace=True)
	return date_df


def get_user_settings(username: int) -> tuple:
	"""Забирает настройки пользователя по его имени"""
	find_user_list = pd.read_sql(f"SELECT username FROM users WHERE username = '{username}'", engine).any()
	if not find_user_list.any():
		username = 999999999
	user_settings = pd.read_sql(
		f"SELECT * FROM user_settings WHERE username = '{username}'",
		engine)
	is_subscribed = user_settings.iloc[0].to_list()[1]
	news_amount = user_settings.iloc[0].to_list()[2]
	is_header = user_settings.iloc[0].to_list()[3]
	user_cat_df = user_settings[['technology', 'science', 'economy', 'entertainment', 'sports', 'society']].T
	user_categories = user_cat_df[user_cat_df[0] != 'False'].index.to_list()
	return user_categories, news_amount, is_subscribed, is_header


def pick_usernews_dict(df: pd.DataFrame, username=999999999) -> dict:
	"""По запрошенному ранее временному df выбираем указываемое число новостей в заданных категориях,
	выбираем один заголовок и одно резюме новости, ссылки на новость сохраняем все. Возвращаем словарь из
	датафреймов новостей для каждой категории новостей.
	"""
	user_categories, news_amount, is_subscribed, is_header = get_user_settings(username)
	base_table = df[['label', 'index', 'date', 'agency', 'category', 'title', 'short_news', 'first_link']]
	base_table['first_link'] = base_table.apply(
		lambda x: (x[7] + ' ' + 'https://t.me/' + x[3] + "/" + str(x[1])) if x[7] != 'NaN' else 'https://t.me/' + x[
			3] + "/" + str(x[1]), axis=1)
	group_table = base_table.groupby('label', sort=False).min()
	temp_dict = {el: base_table.first_link[base_table.label == el].apply(lambda x: set(x.split())).to_list() for el in
	             group_table.index}
	# Ссылки сейчас представлены списком из множеств. Используем распаковку для получения единого множества ссылок
	for k, v in temp_dict.items():
		temp = set()
		temp_dict[k] = temp.union(*v)
	group_table.drop('index', axis=1, inplace=True)
	group_table.reset_index(inplace=True)
	group_table['first_link'] = group_table['label'].apply(lambda x: temp_dict[x])
	group_table.set_index('label', inplace=True)
	user_news_dict = {el: group_table[group_table['category'] == el][:news_amount] for el in user_categories}
	return user_news_dict


def show_title_4category(user_news_dict: dict, category: str) -> dict:
	"""Собирает новости для указанной категории"""
	labels = user_news_dict[category].index.to_list()
	category_news = user_news_dict[category].title.to_list()
	category_news_dict = {k: v for (k, v) in zip(labels, category_news)}
	return category_news_dict


def show_full_news(user_news_dict: dict, category: str, label: int) -> tuple:
	"""Отдаёт подробные сведения о запрошенной новости"""
	short_news = user_news_dict[category].loc[label].short_news
	links = user_news_dict[category].loc[label].first_link
	date = user_news_dict[category].loc[label].date.split('.')[0]  # split по точке из-за нового формата даты в сервисе
	date = str(datetime.strptime(date, '%Y-%m-%d %H:%M:%S').strftime('%d %B %Y - %H:%M:%S'))
	full_news_report = (date, short_news, links)
	return full_news_report
