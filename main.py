import asyncio
import threading

import pandas as pd
import sqlalchemy
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import get_news
import update_db

engine = sqlalchemy.create_engine('sqlite:///db.db')
agencies = pd.read_sql(f"SELECT telegram FROM agencies WHERE is_parsing == 1", con=engine).telegram.to_list()


def run_parsing():
	"""Собирает все свежие новости всех СМИ согласно заданного расписания"""
	scheduler_1 = AsyncIOScheduler(timezone='Europe/Moscow')
	scheduler_1.add_job(get_news.join_all, 'cron', max_instances=10, misfire_grace_time=600, hour=7,
	                    minute=00, kwargs={'agency_list': agencies})
	scheduler_1.add_job(get_news.join_all, 'cron', max_instances=10, misfire_grace_time=600, hour=12,
	                    minute=00, kwargs={'agency_list': agencies})
	scheduler_1.add_job(get_news.join_all, 'cron', max_instances=10, misfire_grace_time=600, hour=17,
	                    minute=00, kwargs={'agency_list': agencies})
	scheduler_1.add_job(get_news.join_all, 'cron', max_instances=10, misfire_grace_time=600, hour=21,
	                    minute=00, kwargs={'agency_list': agencies})
	scheduler_1.add_job(update_db.rename_backup, 'cron', max_instances=10, misfire_grace_time=600, hour=0,
	                    minute=00, args=['db.db'])
	scheduler_1.start()

	asyncio.get_event_loop().run_forever()


if __name__ == "__main__":
	parsing_thread = threading.Thread(target=run_parsing())
	parsing_thread.start()
