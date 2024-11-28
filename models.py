# models.py
from datetime import datetime
from typing import Text

import bcrypt
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index, event, text

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
    files = db.relationship('ProjectFile', back_populates='project', lazy=True)
    stages = db.relationship('ProjectStage', back_populates='project', lazy=True)
    updates = db.relationship('ProjectUpdate', back_populates='project')


# 项目阶段表

class ProjectStage(db.Model):
    __tablename__ = 'project_stages'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    progress = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)

    # 关系
    project = db.relationship('Project', back_populates='stages')
    stage_files = db.relationship('ProjectFile', back_populates='stage', lazy=True)  # 修改为 stage_files
    tasks = db.relationship('StageTask', back_populates='stage', lazy=True)


# 阶段更新表
class ProjectUpdate(db.Model):
    __tablename__ = 'project_updates'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    progress = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    type = db.Column(db.String(50))

    # 关联
    project = db.relationship('Project', back_populates='updates')


# 修改ProjectFile模型
class ProjectFile(db.Model):
    __tablename__ = 'project_files'
    id = db.Column(db.Integer, primary_key=True)
    original_name = db.Column(db.String(255))
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    stage_id = db.Column(db.Integer, db.ForeignKey('project_stages.id'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('stage_tasks.id'), nullable=True)
    file_name = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(100))
    file_path = db.Column(db.String(255), nullable=False)
    upload_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    upload_date = db.Column(db.DateTime, nullable=False, default=datetime.now)
    text_extracted = db.Column(db.Boolean, default=False)

    # 关联
    upload_user = db.relationship('User', backref='uploaded_files')
    project = db.relationship('Project', back_populates='files')
    stage = db.relationship('ProjectStage', back_populates='stage_files')
    task = db.relationship('StageTask', backref='files')
    content = db.relationship('FileContent', backref='file', uselist=False,
                              cascade='all, delete-orphan')


# 阶段任务表
class StageTask(db.Model):
    __tablename__ = 'stage_tasks'

    id = db.Column(db.Integer, primary_key=True)
    stage_id = db.Column(db.Integer, db.ForeignKey('project_stages.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    due_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='pending')  # 待处理、正在进行、已完成
    progress = db.Column(db.Integer, default=0)  # 进度
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    stage = db.relationship('ProjectStage', back_populates='tasks')
    progress_updates = db.relationship('TaskProgressUpdate', back_populates='task', cascade='all, delete-orphan')


# 编辑时间跟踪表
class EditTimeTracking(db.Model):
    __tablename__ = 'edit_time_tracking'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    edit_type = db.Column(db.String(20), nullable=False)  # 'stage' or 'task'
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    duration = db.Column(db.Integer, nullable=False)  # 持续时间（秒）
    stage_id = db.Column(db.Integer, db.ForeignKey('project_stages.id'), nullable=True)
    task_id = db.Column(db.Integer, db.ForeignKey('stage_tasks.id'), nullable=True)

    # 关系
    project = db.relationship('Project', backref='edit_tracks')
    user = db.relationship('User', backref='edit_tracks')
    stage = db.relationship('ProjectStage', backref='edit_tracks')
    task = db.relationship('StageTask', backref='edit_tracks')


# 补卡记录表
class ReportClockin(db.Model):
    __tablename__ = 'report_clockins'

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    report_date = db.Column(db.DateTime, nullable=False, default=datetime.now())
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now())

    # 关联
    employee = db.relationship('User', backref='report_clockins')
    details = db.relationship('ReportClockinDetail', backref='report', cascade='all, delete-orphan')

    @classmethod
    def has_reported_this_month(cls, employee_id):
        """检查用户本月是否已经提交过补卡申请"""
        today = datetime.now()
        start_of_month = datetime(today.year, today.month, 1)
        end_of_month = datetime(today.year, today.month + 1, 1) if today.month < 12 else datetime(today.year + 1, 1, 1)

        return db.session.query(cls).filter(
            cls.employee_id == employee_id,
            cls.report_date >= start_of_month,
            cls.report_date < end_of_month
        ).first() is not None


# 补卡明细表
class ReportClockinDetail(db.Model):
    __tablename__ = 'report_clockin_details'

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('report_clockins.id'), nullable=False)
    clockin_date = db.Column(db.Date, nullable=False)  # 补卡日期
    weekday = db.Column(db.String(20), nullable=False)  # 星期几
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now())


# 任务更新表
class TaskProgressUpdate(db.Model):
    __tablename__ = 'task_progress_updates'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('stage_tasks.id'), nullable=False)
    progress = db.Column(db.Integer, nullable=False)  # 进度百分比
    description = db.Column(db.String(255), nullable=True)  # 更新内容说明
    created_at = db.Column(db.DateTime, default=datetime.now)  # 更新时间
    # 关系
    task = db.relationship('StageTask', back_populates='progress_updates')


# 创建FTS5虚拟表的事件监听器
def create_fts_table(target, connection, **kw):
    connection.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS file_contents_fts 
        USING fts5(
            content,
            tokenize='porter unicode61'
        )
    """)


# 文件内容全文搜索表 - 使用普通表存储
class FileContent(db.Model):
    __tablename__ = 'file_contents'

    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.Integer, db.ForeignKey('project_files.id', ondelete='CASCADE'), unique=True)
    content = db.Column(db.Text)

    def after_insert(self, connection):
        try:
            # 尝试使用FTS5
            stmt = text('INSERT INTO file_contents_fts (rowid, content) VALUES (:id, :content)')
            connection.execute(stmt, {'id': self.id, 'content': self.content})
        except Exception:
            try:
                # 如果失败，尝试使用FTS4
                stmt = text('INSERT INTO file_contents_fts (docid, content) VALUES (:id, :content)')
                connection.execute(stmt, {'id': self.id, 'content': self.content})
            except Exception:
                # 如果全文搜索不可用，就跳过索引创建
                pass

    def after_update(self, connection):
        try:
            stmt = text('UPDATE file_contents_fts SET content = :content WHERE rowid = :id')
            connection.execute(stmt, {'content': self.content, 'id': self.id})
        except Exception:
            try:
                stmt = text('UPDATE file_contents_fts SET content = :content WHERE docid = :id')
                connection.execute(stmt, {'content': self.content, 'id': self.id})
            except Exception:
                pass

    def after_delete(self, connection):
        try:
            stmt = text('DELETE FROM file_contents_fts WHERE rowid = :id')
            connection.execute(stmt, {'id': self.id})
        except Exception:
            try:
                stmt = text('DELETE FROM file_contents_fts WHERE docid = :id')
                connection.execute(stmt, {'id': self.id})
            except Exception:
                pass
