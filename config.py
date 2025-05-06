# config.py
import os
import platform
import sys
import shutil
import time
import zipfile

from flask import Flask
from flask_cors import CORS
from flask_migrate import Migrate
from models import db

# APScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# === 备份函数 ===

def backup_folders():
    source_dirs = {
        'FileManagementFolder': '/volume1/web/FileManagementFolder',
        'FileManagement': '/volume1/web/FileManagement',
        'Dist': '/volume1/docker/nginx',  # 前端打包文件
    }
    backup_dir = '/volume1/web/backup'
    # 最多保留5份
    max_backups = 5

    try:
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)

        timestamp = time.strftime("%Y%m%d_%H%M%S")

        for name, path in source_dirs.items():
            zip_filename = os.path.join(backup_dir, f"{name}_backup_{timestamp}.zip")
            with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(path):
                    for file in files:
                        abs_path = os.path.join(root, file)
                        relative_path = os.path.relpath(abs_path, path)
                        zipf.write(abs_path, arcname=relative_path)

            print(f"{path} 已备份到 {zip_filename}")
            clean_old_backups(backup_dir, name, max_backups)

    except Exception as e:
        print(f"备份过程中出错: {e}")


def clean_old_backups(backup_dir, name_prefix, max_backups):
    """清理旧的备份文件，只保留最新的 max_backups 个"""
    backups = []
    for file in os.listdir(backup_dir):
        if file.startswith(name_prefix) and file.endswith('.zip'):
            full_path = os.path.join(backup_dir, file)
            backups.append((os.path.getctime(full_path), full_path))

    backups.sort(reverse=True)

    for i in range(max_backups, len(backups)):
        try:
            os.remove(backups[i][1])
            print(f"已删除旧备份: {backups[i][1]}")
        except Exception as e:
            print(f"删除备份文件时出错: {e}")


# === 启动 APScheduler 定时任务 ===

def start_backup_scheduler():
    scheduler = BackgroundScheduler()
    trigger = CronTrigger(hour=2, minute=0)  # 每天凌晨 2 点
    scheduler.add_job(backup_folders, trigger, id="daily_backup", replace_existing=True)
    scheduler.start()
    print("定时备份任务已启动（每天凌晨 2 点）")


# === Flask 应用初始化 ===

def create_app():
    app = Flask(__name__)
    CORS(app)

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = '9888898888'

    migrate = Migrate(app, db)

    system_platform = platform.system()
    if system_platform == 'Windows':
        print("当前环境：Windows（开发环境）")
        python_dir = os.path.dirname(sys.executable)
        db_path = os.path.join(python_dir, 'project.db')
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    else:
        print("当前环境：Linux（生产环境）")
        python_dir = '/volume1/web/FileManagementFolder/db'
        db_path = os.path.join(python_dir, 'project.db')
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'

    db.init_app(app)

    return app


# 创建 app 实例
app = create_app()
