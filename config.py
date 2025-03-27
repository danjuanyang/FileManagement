# config.py
import os
import sys

from flask import Flask
from flask_cors import CORS
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from models import db

def create_app():
    app = Flask(__name__)
    CORS(app)

    # 获取Python解释器所在目录
    python_dir = os.path.dirname(sys.executable)
    # 构建数据库文件路径
    db_path = os.path.join(python_dir, 'project.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = '9888898888'


    migrate = Migrate(app, db)




    # 群晖路径
    # 获取Python解释器所在目录
    # python_dir = '/volume1/web/FileManagementFolder/db'
    # # 构建数据库文件路径
    # db_path = os.path.join(python_dir, 'project.db')
    # app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'



    # 初始化数据库
    db.init_app(app)

    return app


app = create_app()
