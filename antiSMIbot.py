import telebot
from telebot.apihelper import ApiTelegramException

from push_news import *
import schedule
import time
import threading

token = "YOUR TOKEN"
bot = telebot.TeleBot(token=token)

start_text = ('🤖 Выбери меню "news" (новости на сегодня), введи другую дату или пришли геопозицию.\n'
              '📗 Подробнее в меню "help".\n'
              'Знаю тысячи источников, но работаю в тестовом режиме с ограниченным количеством СМИ, '
              'понятных и приятных моему хозяину. '
              'Будет запрос - расширимся быстро!')

help_text = ("🤖 Инструкция по применению 📗\n"
             "запрос/подписка 👉 сводка новостных заголовков по категориям 👉 подробная новость по запросу\n\n"
             "1. Способы получить сводку:\n"
             "а. Через меню \"news\": на текущую дату придут три актуальных заголовка из каждой категории (кроме "
             "политики).\n"
             "b. Через отправку своей геопозиции: тот же результат + оформится стандартная подписка (см. ниже). Если "
             "уже была оформлена, просто придёт порция свежих новостей согласно твоим настойкам.\n"
             "c. Получить сводку на определенную дату -  ввести дату в формате \"ГГГГ-ММ-ДД\" (2022-07-20).\n"
             "Новости до 1 июля 2022 года показать не смогу: бот научился их собирать только в конце июня.\n\n"
             "2. Подписка:\n"
             "/бесплатна, даёт возможность 4 раза в день получать свою свежую новостную сводку/\n"
             "a. Самый простой способ подписаться - прислать геопозицию (оформится стандартная подписка: будут "
             "приходить по три новости из всех рубрик без политики).\n"
             "b. Более скучный, но правильный способ подписки - через меню \"subscribe\" и \"settings\":\n"
             "позволяет настроить любимые рубрики и количество получаемых из каждой рубрики новостей.\n"
             "с. Выбрать для себя категории и количество новостей за раз получится только оформив подписку.\n\n"
             "3. Получить новость.\n"
             "/можно изучить новость подробно и почитать первоисточники по заинтересовавшему тебя заголовку/\n"
             "а. Сводка новостей приходит сгруппированной по рубрикам, в рамках каждой из которых идут заголовки "
             "новостей. И рубрики, и заголовки пронумерованы ботом (заголовки пронумерованы странно: не спрашивай, "
             "так было нужно).\n"
             "b. Если заинтересовала конкретная новость и нужно погрузиться - направь боту \"координаты\" новости:"
             "две цифры через пробел в формате \"номер_рубрики\" \"номер_новости\"\n"
             "c. Бот пришлёт развернутое описание новости + все ссылки на первоисточники на эту и похожую новости.\n\n"
             "Ограничения:\n"
             "Работаем в тестовом режиме с небольшим количеством СМИ. Можем с огромным, но не уверены, что надо. "
             "Появится ваш интерес - будем расширяться!")


def user_digest(username, parse_date=str(datetime.now().date()), part_number=0):
	"""Отдаёт подборку новостей пользователя согласно его настройкам и за заданный период"""
	input_date = datetime.strptime(parse_date, '%Y-%m-%d').date()
	greeting = {1: 'утренняя', 2: 'дневная', 3: 'вечерняя', 4: 'ночная'}
	if input_date > datetime.now().date() or input_date < datetime.strptime('2022-06-28', '%Y-%m-%d').date():
		bot.send_message(username,
		                 f'🤖📗 Вы ввели дату из далёкого будущего или глубокого прошлого, а тут я бессилен')
	else:
		user_categories, news_amount, is_subscribed, is_header = get_user_settings(username)
		date_df = show_date(parse_date, part_number)
		first_name = pd.read_sql(f"SELECT first_name FROM users WHERE username = '{username}'", engine).first_name[0]
		if part_number != 0:
			my_news = f'🤖: {first_name}, привет!\n\nТвоя {greeting[part_number]} подборка на\n' \
			          f'{datetime.strptime(parse_date, "%Y-%m-%d").strftime("%d %B %Y")}: 👇\n'
		else:
			my_news = f'🤖: {first_name}, привет!\n\nТвоя подборка за\n' \
			          f'{datetime.strptime(parse_date, "%Y-%m-%d").strftime("%d %B %Y")}: 👇\n'

		if is_subscribed == 'True':
			user_news_dict = pick_usernews_dict(date_df, username)
		else:
			user_news_dict = pick_usernews_dict(date_df)
		for i, category in enumerate(user_categories):
			russian_title = \
				pd.read_sql(f"SELECT russian_title FROM categories WHERE category = '{category}'",
				            engine).russian_title[0]
			emoj = pd.read_sql(f"SELECT emoj FROM categories WHERE category = '{category}'", engine).emoj[0]
			category_news = show_title_4category(user_news_dict, category)
			if category_news:
				category_title = f'\n{emoj} {i + 1}. {russian_title.capitalize()}:\n'
				my_news += category_title
				for labels, news in category_news.items():
					my_news += f'{labels}. {news}\n'

		bot.send_message(username, my_news)
		# Пишем дату последнего дайджеста в специальную таблицу в базе
		digest_data = {'username': username, 'digest_date': parse_date, 'part_number': part_number}
		digest_df = pd.DataFrame(digest_data, index=[0])
		digest_df.to_sql(name='user_digest', con=engine, if_exists='append', index=False)


# bot.send_message(username,
#                  f'📌 По заголовку можно прочесть новость подробно: \n'
#                  f'отправь координаты через пробел\n'
#                  f'("5 7" направит 7-ую новость 5-ой рубрики)')


def get_full_news(username, message):
	"""Выдаёт полную новость и ссылки на неё"""
	digest_date = pd.read_sql(f"SELECT digest_date FROM user_digest WHERE username = '{username}'", engine).digest_date[
		0]
	digest_part = pd.read_sql(f"SELECT part_number FROM user_digest WHERE username = '{username}'", engine).part_number[
		0]
	markdown = """*bold text*"""
	try:
		user_categories, news_amount, is_subscribed, is_header = get_user_settings(username)
		category_number, label = map(int, message.split(' '))
		category = user_categories[category_number - 1]
		date_df = show_date(digest_date, digest_part)
		if is_subscribed == 'True':
			user_news_dict = pick_usernews_dict(date_df, username)
		else:
			user_news_dict = pick_usernews_dict(date_df)
		news_title = user_news_dict[category][['title']].loc[label].title
		full_news = show_full_news(user_news_dict, category, label)
		full_digest = f'🤖 {full_news[0]} 🤖\n\n*{news_title}*\n\n{full_news[1].replace(news_title +". ", "")}' \
		              f'\n\n👇 СМИ и первоисточники 👇'

		bot.send_message(username, full_digest, parse_mode="Markdown")
		full_news[2].discard('https://t.me/economika')
		for link in full_news[2]:
			bot.send_message(username, link)

	except Exception:
		bot.send_message(username, f'⚠ Неправильно введена координата новости.\n'
		                           f'📗 Нужно ввести еще раз, или почитать инструкцию к боту (команда "help")')


def redefine_user_settings(username, categories_letter, news_amount):
	subscribed_users = pd.read_sql(f"SELECT username FROM user_settings WHERE is_subscribed = 'True'", engine)
	subscribed_users = subscribed_users.username.to_list()

	if username in subscribed_users:
		category_df = pd.read_sql(f"SELECT category, russian_title FROM categories", con=engine)
		new_category = [category_df.category[category_df.russian_title.str.startswith(el.lower())].iloc[0] for el in
		                categories_letter]

		user_settings = pd.read_sql(f"SELECT * FROM user_settings WHERE username = '{username}'", engine)
		#  Переводим все категорию в False, а затем присваиваем True только тем из них, который указал пользователь
		user_settings[['technology', 'science', 'economy', 'entertainment', 'sports', 'society']] = 'False'
		for category in new_category:
			user_settings[category].iloc[0] = 'True'
		user_settings['news_amount'].iloc[0] = news_amount
		user_settings.to_sql(name='user_settings', con=engine, if_exists='append', index=False)
		return user_settings


@bot.message_handler(commands=['start'])
def handle_start(message):
	username = message.chat.id
	bot.send_message(username, start_text)


@bot.message_handler(commands=['help'])
def handle_help(message):
	"""Выводит сообщение с инструкцией к боту"""
	username = message.chat.id
	bot.send_message(username, help_text)


@bot.message_handler(commands=['subscribe'])
def handle_subscribe(message):
	"""Собирает сведения о пользователе и пишет в базу данных"""

	username = message.chat.id
	nickname = message.from_user.username
	first_name = message.from_user.first_name
	last_name = message.from_user.last_name
	subscribe_date = str(datetime.now().date())
	success_subscribed_text = (f"Успешно подписался, {nickname}, спасибо! ❤\n\n"
	                           "Теперь 4 раза в день тебе будет ждать свежая порция новостей.\n\n"
	                           "По умолчанию приходит стандартная сводка: \n"
	                           "- все типы новостей (кроме политики); \n"
	                           "- по три новости в каждой категории.\n\n"
	                           "Изменить параметры можно в настройках.\n\n"
	                           "Хорошего дня!")

	user_dict = {'username': username, 'nickname': nickname, 'first_name': first_name, 'last_name': last_name,
	             'subscribe_date': subscribe_date}
	user_df = pd.DataFrame(user_dict, index=[0])
	all_users = pd.read_sql(f"SELECT username FROM user_settings", engine)
	all_users = all_users.username.to_list()
	subscribed_users = pd.read_sql(f"SELECT username FROM user_settings WHERE is_subscribed = 'True'", engine)
	subscribed_users = subscribed_users.username.to_list()
	#  если пользователя подписывается впервые
	if username not in all_users:
		# Завели пользователя в users
		user_df.to_sql(name='users', con=engine, if_exists='append', index=False)
		# Завели настройки для этого пользователя == дефолтным
		default_settings = pd.read_sql(f"SELECT * FROM user_settings WHERE username = 999999999", engine)
		user_settings = default_settings
		user_settings.username = username
		user_settings.is_subscribed = 'True'
		user_settings.to_sql(name='user_settings', con=engine, if_exists='append', index=False)
		bot.send_message(username, success_subscribed_text)
	#  если пользователь подписывался раннее, но отписался
	elif username not in subscribed_users:
		user_settings = pd.read_sql(f"SELECT * FROM user_settings WHERE username = '{username}'", engine)
		user_settings.is_subscribed = 'True'
		user_settings.to_sql(name='user_settings', con=engine, if_exists='append', index=False)
		bot.send_message(username, success_subscribed_text)

	#  если пользователь зачем-то захотел подписаться повторно
	else:
		# bot.send_message(username, f"Вы уже подписаны.")
		pass


@bot.message_handler(commands=['unsubscribe'])
def handle_unsubscribe(message):
	"""Отписка от рассылки путем снятия пользовательского флага об участии в рассылке"""
	username = message.chat.id
	nickname = message.from_user.username
	subscribed_users = pd.read_sql(f"SELECT username FROM user_settings WHERE is_subscribed = 'True'", engine)
	subscribed_users = subscribed_users.username.to_list()
	if username in subscribed_users:
		user_settings = pd.read_sql(f"SELECT * FROM user_settings WHERE username = '{username}'", engine)
		user_settings.is_subscribed = 'False'
		user_settings.to_sql(name='user_settings', con=engine, if_exists='append', index=False)
		bot.send_message(username, f"Спасибо что был с нами, {nickname}! Удачи!")


@bot.message_handler(commands=['news'])
def handle_news(message):
	"""Отдаёт пользовательскую подборку"""
	username = message.chat.id  # temp_dict автора сообщения
	user_date = str(datetime.now().date())
	user_digest(username, parse_date=user_date, part_number=0)


@bot.message_handler(content_types=['location'])
def handle_loc(message):
	username = message.chat.id
	coord = (message.location.latitude, message.location.longitude)
	timestamp = str(datetime.now())
	user_coord_dict = {'username': username, 'coord': str(coord), 'timestamp': timestamp}
	df = pd.DataFrame(user_coord_dict, index=[0])
	df.to_sql(name='users_coord', con=engine, if_exists='append', index=False)

	handle_subscribe(message)
	user_digest(username)


@bot.message_handler(commands=['settings'])
def handle_settings(message):
	"""Даёт подписанным пользователям инструкцию по изменению настроек по умолчанию"""
	username = message.chat.id
	nickname = message.from_user.username

	subscribed_users = pd.read_sql(f"SELECT username FROM user_settings WHERE is_subscribed = 'True'", engine)
	subscribed_users = subscribed_users.username.to_list()

	if username in subscribed_users:
		settings_text = (f"Как знаешь, стандартная настройка - 3 новости без политики.\n"
		                 f"Здесь рассказано, как изменить категории и количество новостей в каждой категории.\n"
		                 f"📗 Настройка пока сложная, {nickname}, прочти внимательно!\n\n"
		                 f"🤖 Я умею собирать шесть категорий новостей, каждая из которых начинается со своей буквы:\n"
		                 f"Н - Наука\n"
		                 f"П - Политика и общество\n"
		                 f"Р - Развлечения\n"
		                 f"С - Спорт\n"
		                 f"Т - Технологии и IT\n"
		                 f"Э - Экономика\n\n"
		                 f""
		                 f'Чтобы это изменить, нужно направить мне новые настройки в формате "буквы_слитно" "число"\n'
		                 f'Например, "СТЭ 5" позволит получать по пять новостей спорта, технологий и экономики\n'
		                 f'Остальные категории будут игнорироваться, пока не изменишь настройки ещё раз\n\n'
		                 f'P.S. Название букв можно вводить в любом регистре и последовательности, но только слитно.\n'
		                 f' Нельзя послать только буквы или только число')
		bot.send_message(username, settings_text)
	else:
		bot.send_message(username, 'Чтобы получить доступ с настройкам, нужно подписаться')


@bot.message_handler(content_types=['text'])
def guess_user_request(message):
	"""Пытается угадать желания пользователя по полученному от него сообщению"""
	username = message.chat.id
	answer = message.text
	try:
		valid_date = datetime.strptime(answer, '%Y-%m-%d')
		user_digest(username, parse_date=answer)
	except ValueError:
		try:
			if answer[0].isdigit():
				category_number, label = map(int, answer.split(' '))
				get_full_news(username, answer)
			elif answer[0].isalpha():
				categories_letter = answer.split(' ')[0]
				news_amount = int(answer.split(' ')[1])
				new_user_settings = redefine_user_settings(username, categories_letter, news_amount)
				if type(new_user_settings) == pd.DataFrame and not new_user_settings.empty:
					bot.send_message(username, 'Новые настройки применены')
				else:
					bot.send_message(username, 'Что-то пошло не так')

		except ValueError:
			bot.send_message(username,
			                 '⚠ Могу обрабатывать только дату (формат ГГГГ-ММ-ДД) или координаты новости (два '
			                 'числа через пробел).\n'
			                 '📗 Нужно ввести еще раз, или почитать инструкцию к боту (команда "help")')


def sending_news(part_number):
	subscribed_users_df = pd.read_sql(f"SELECT username FROM user_settings WHERE is_subscribed = 'True'", con=engine)
	if not subscribed_users_df.empty:
		subscribed_users_dict = subscribed_users_df.T.to_dict()
		parse_date = str(datetime.now().date())
		for users in subscribed_users_dict.values():
			username = users['username']
			try:
				user_digest(username, parse_date, part_number)
			except ApiTelegramException as e:
				if e.description == "Forbidden: bot was blocked by the user":
					print(f"Пользователь {users} забанил бот.")


def run_bot():
	while True:
		try:
			bot.polling(none_stop=True)
		except Exception:
			pass


def run_sending_news():
	try:
		schedule.every().day.at("08:00").do(sending_news, 1)
		schedule.every().day.at("13:00").do(sending_news, 2)
		schedule.every().day.at("18:00").do(sending_news, 3)
		schedule.every().day.at("22:00").do(sending_news, 4)
	except Exception:
		pass

	# Start cron task after some time interval
	while True:
		schedule.run_pending()
		time.sleep(1)


if __name__ == "__main__":
	try:
		bot_thread = threading.Thread(target=run_bot)
		sending_thread = threading.Thread(target=run_sending_news)

		bot_thread.start()
		sending_thread.start()
	except:
		pass
