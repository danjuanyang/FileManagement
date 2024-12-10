# config.py
import os
import sys

from flask import Flask
from flask_cors import CORS
from sqlalchemy import event

from models import db


# # 获取Python解释器所在目录
# python_dir = os.path.dirname(sys.executable)
# # 构建数据库文件路径
# db_path = os.path.join(python_dir, 'project.db')

# # 测试用：路径在程序的File\FileManagement\instance下
# # app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///project.db'
# # 正式环境：使用绝对路径配置数据库URI

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
