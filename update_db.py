import shutil
import os
from datetime import datetime


def make_file_backup(filename: str):
	"""Делает копию задаваемого файла в директорию backups"""
	file_source = filename
	file_destination = 'backups/'
	shutil.copy(file_source, file_destination)


async def rename_backup(filename: str):
	date = str(datetime.now().date())
	os.rename(f'backups/{filename}', f'backups/{date} {filename}')
