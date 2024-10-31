# models.py
from datetime import datetime

import bcrypt
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


# 用户表
class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.Integer, nullable=False)

    def set_password(self, password):
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_password(self, password):
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))

# models.py

# 项目表
class Project(db.Model):
    __tablename__ = 'projects'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    employee_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    deadline = db.Column(db.DateTime, nullable=False)
    progress = db.Column(db.Float, default=0.0)  # 0-100
    status = db.Column(db.String(20), default='pending')  # 待处理、正在干、已完成

    # 关联
    employee = db.relationship('User', backref='projects')
    files = db.relationship('ProjectFile', backref='project', lazy=True)
    stages = db.relationship('ProjectStage', back_populates='project', lazy=True)
    updates = db.relationship('ProjectUpdate', back_populates='project')


# 项目文件表
class ProjectFile(db.Model):
    __tablename__ = 'project_files'

    id = db.Column(db.Integer, primary_key=True)
    file_name = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(50))
    file_url = db.Column(db.String(255))
    file_size = db.Column(db.Integer)  # in bytes
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'))
    upload_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)

    upload_user = db.relationship('User', backref='uploaded_files')


# 项目阶段表
class ProjectStage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    progress = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)

    project = db.relationship('Project', back_populates='stages')

# 阶段更新表
class ProjectUpdate(db.Model):
    __tablename__ = 'project_updates'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)  # Corrected table name
    progress = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    type = db.Column(db.String(50))

    project = db.relationship('Project', back_populates='updates')
