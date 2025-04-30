# config.py
import os
import platform
import sys
import shutil
import threading
import time
import zipfile

from flask import Flask
from flask_cors import CORS
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from models import db


# === 新增备份相关函数（注意：必须在 create_app 之前定义） ===

def backup_folders():
    source_dirs = {
        'FileManagementFolder': '/volume1/web/FileManagementFolder',
        'FileManagement': '/volume1/web/FileManagement'
    }
    backup_dir = '/volume1/web/backup'
    max_backups = 5  # 最多保留5份

    while True:
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

                # 清理多余备份
                clean_old_backups(backup_dir, name, max_backups)

        except Exception as e:
            print(f"备份过程中出错: {e}")

        # 每3天备份一次
        time.sleep(3 * 24 * 60 * 60)


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


def start_backup_thread():
    backup_thread = threading.Thread(target=backup_folders, daemon=True)
    backup_thread.start()


# === 原来的 create_app 代码，基本不动 ===

def create_app():
    app = Flask(__name__)
    CORS(app)

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = '9888898888'

    migrate = Migrate(app, db)

    # 根据操作系统选择数据库路径
    system_platform = platform.system()
    if system_platform == 'Windows':
        # Windows开发环境
        print("当前环境：Windows（开发环境）")
        python_dir = os.path.dirname(sys.executable)
        db_path = os.path.join(python_dir, 'project.db')
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    else:
        # Linux生产环境（群晖）
        print("当前环境：Linux（生产环境）")
        python_dir = '/volume1/web/FileManagementFolder/db'
        db_path = os.path.join(python_dir, 'project.db')
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'

    # 初始化数据库
    db.init_app(app)

    return app


app = create_app()
