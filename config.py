# config.py
import os
import sys

from flask import Flask
from flask_cors import CORS
from models import db

app = Flask(__name__)
CORS(app)

# 获取Python解释器所在目录
python_dir = os.path.dirname(sys.executable)
# 构建数据库文件路径
db_path = os.path.join(python_dir, 'project.db')

# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///project.db'
# 使用绝对路径配置数据库URI
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = '9888898888'

db.init_app(app)