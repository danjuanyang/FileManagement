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

    # Add new field for team leader relationship
    team_leader_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    def set_password(self, password):
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_password(self, password):
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))


class Project(db.Model):
    __tablename__ = 'projects'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    # employee_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    employee_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    start_date = db.Column(db.DateTime, default=datetime.now)
    deadline = db.Column(db.DateTime, nullable=False)
    progress = db.Column(db.Float, default=0.0)  # 0-100
    status = db.Column(db.String(20), default='pending')  # 待处理、正在干、已完成

    # 关联
    # employee = db.relationship('User', backref='projects')
    employee = db.relationship('User', backref=db.backref('projects', passive_deletes=True))
    files = db.relationship('ProjectFile', back_populates='project', lazy=True)
    # stages = db.relationship('ProjectStage', back_populates='project', lazy=True)
    stages = db.relationship('ProjectStage', back_populates='project', lazy=True)
    updates = db.relationship('ProjectUpdate', back_populates='project')


# 2025年3月17日14:15:37
# 子项目表
# class Subproject(db.Model):
#     __tablename__ = 'subprojects'
#
#     id = db.Column(db.Integer, primary_key=True)
#     name = db.Column(db.String(100), nullable=False)
#     description = db.Column(db.Text)
#     project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
#     start_date = db.Column(db.DateTime, default=datetime.now)
#     deadline = db.Column(db.DateTime, nullable=False)
#     progress = db.Column(db.Float, default=0.0)  # 0-100
#     status = db.Column(db.String(20), default='pending')  # 待处理、正在干、已完成
#     created_at = db.Column(db.DateTime, default=datetime.now)
#     updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
#
#     # 关系
#     project = db.relationship('Project', backref=db.backref('subprojects', lazy=True, cascade='all, delete-orphan'))
#     stages = db.relationship('ProjectStage', back_populates='subproject', lazy=True, cascade='all, delete-orphan')

# In models.py, update Subproject class
class Subproject(db.Model):
    __tablename__ = 'subprojects'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    start_date = db.Column(db.DateTime, default=datetime.now)
    deadline = db.Column(db.DateTime, nullable=False)
    progress = db.Column(db.Float, default=0.0)  # 0-100
    status = db.Column(db.String(20), default='pending')  # 待处理、正在干、已完成
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # 关系
    project = db.relationship('Project', backref=db.backref('subprojects', lazy=True, cascade='all, delete-orphan'))
    employee = db.relationship('User', backref=db.backref('assigned_subprojects', lazy=True))
    stages = db.relationship('ProjectStage', back_populates='subproject', lazy=True, cascade='all, delete-orphan')


# 项目阶段表
# class ProjectStage(db.Model):
#     __tablename__ = 'project_stages'
#
#     id = db.Column(db.Integer, primary_key=True)
#     name = db.Column(db.String(50), nullable=False)
#     description = db.Column(db.String(200), nullable=False)
#     start_date = db.Column(db.Date, nullable=False)
#     end_date = db.Column(db.Date, nullable=False)
#     progress = db.Column(db.Integer, nullable=False)
#     status = db.Column(db.String(20), nullable=False)
#     subproject_id = db.Column(db.Integer, db.ForeignKey('subprojects.id', ondelete='CASCADE'), nullable=False)
#     # 保留 project_id 以实现向后兼容性或快速查找
#     project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
#
#     # 关系
#     # project = db.relationship('Project', backref=db.backref('stages', passive_deletes=True))
#     project = db.relationship('Project', back_populates='stages')
#     subproject = db.relationship('Subproject', back_populates='stages')
#     stage_files = db.relationship('ProjectFile', back_populates='stage', lazy=True)
#     tasks = db.relationship('StageTask', back_populates='stage', lazy=True, cascade='all, delete-orphan')

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
    subproject_id = db.Column(db.Integer, db.ForeignKey('subprojects.id', ondelete='CASCADE'), nullable=False)
    # 保留 project_id 以实现向后兼容性或快速查找
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)

    # 关系
    project = db.relationship('Project', back_populates='stages')
    subproject = db.relationship('Subproject', back_populates='stages')
    stage_files = db.relationship('ProjectFile', back_populates='stage', lazy=True)
    tasks = db.relationship('StageTask', back_populates='stage', lazy=True, cascade='all, delete-orphan')


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
# class ProjectFile(db.Model):
#     __tablename__ = 'project_files'
#     id = db.Column(db.Integer, primary_key=True)
#     original_name = db.Column(db.String(255))
#     project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
#     stage_id = db.Column(db.Integer, db.ForeignKey('project_stages.id'), nullable=False)
#     task_id = db.Column(db.Integer, db.ForeignKey('stage_tasks.id'), nullable=True)
#     file_name = db.Column(db.String(255), nullable=False)
#     file_type = db.Column(db.String(100))
#     file_path = db.Column(db.String(255), nullable=False)
#     # upload_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
#     upload_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
#     upload_date = db.Column(db.DateTime, nullable=False, default=datetime.now)
#     text_extracted = db.Column(db.Boolean, default=False)
#     is_public = db.Column(db.Boolean, default=False)  # 是否公开
#
#     # 关联
#     # upload_user = db.relationship('User', backref='uploaded_files')
#     upload_user = db.relationship('User', backref=db.backref('uploaded_files', passive_deletes=True))
#     project = db.relationship('Project', back_populates='files')
#     stage = db.relationship('ProjectStage', back_populates='stage_files')
#     task = db.relationship('StageTask', backref='files')
#     content = db.relationship('FileContent', backref='file', uselist=False,
#                               cascade='all, delete-orphan')


class ProjectFile(db.Model):
    __tablename__ = 'project_files'
    id = db.Column(db.Integer, primary_key=True)
    original_name = db.Column(db.String(255))
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    subproject_id = db.Column(db.Integer, db.ForeignKey('subprojects.id'), nullable=False)
    stage_id = db.Column(db.Integer, db.ForeignKey('project_stages.id'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('stage_tasks.id'), nullable=True)
    file_name = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(100))
    file_path = db.Column(db.String(255), nullable=False)
    upload_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    upload_date = db.Column(db.DateTime, nullable=False, default=datetime.now)
    text_extracted = db.Column(db.Boolean, default=False)
    is_public = db.Column(db.Boolean, default=False)  # 是否公开

    # 关系
    upload_user = db.relationship('User', backref=db.backref('uploaded_files', passive_deletes=True))
    project = db.relationship('Project', back_populates='files')
    subproject = db.relationship('Subproject', backref='files')
    stage = db.relationship('ProjectStage', back_populates='stage_files')
    task = db.relationship('StageTask', backref='files')
    content = db.relationship('FileContent', backref='file', uselist=False, cascade='all, delete-orphan')


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
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # 关系
    stage = db.relationship('ProjectStage', back_populates='tasks')
    progress_updates = db.relationship('TaskProgressUpdate', back_populates='task', cascade='all, delete-orphan')


# 编辑时间跟踪表
class EditTimeTracking(db.Model):
    __tablename__ = 'edit_time_tracking'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    subproject_id = db.Column(db.Integer, db.ForeignKey('subprojects.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    edit_type = db.Column(db.String(20), nullable=False)  # 'subproject', 'stage', or 'task'
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    duration = db.Column(db.Integer, nullable=False)  # 持续时间（秒）
    stage_id = db.Column(db.Integer, db.ForeignKey('project_stages.id'), nullable=True)
    task_id = db.Column(db.Integer, db.ForeignKey('stage_tasks.id'), nullable=True)

    # 关系
    project = db.relationship('Project', backref='edit_tracks')
    subproject = db.relationship('Subproject', backref='edit_tracks')
    user = db.relationship('User', backref=db.backref('edit_tracks', passive_deletes=True))
    stage = db.relationship('ProjectStage', backref='edit_tracks')
    task = db.relationship('StageTask', backref='edit_tracks')


# 补卡记录表
class ReportClockin(db.Model):
    __tablename__ = 'report_clockins'

    id = db.Column(db.Integer, primary_key=True)
    # employee_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    report_date = db.Column(db.DateTime, nullable=False, default=datetime.now())
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now())

    # 关联
    employee = db.relationship('User', backref=db.backref('report_clockins', passive_deletes=True))
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
    remarks = db.Column(db.String(200))  # 补卡备注
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now())


# 任务更新表
class TaskProgressUpdate(db.Model):
    __tablename__ = 'task_progress_updates'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('stage_tasks.id'), nullable=False)
    progress = db.Column(db.Integer, nullable=False)  # 进度百分比
    description = db.Column(db.String(255), nullable=True)  # 更新内容说明
    created_at = db.Column(db.DateTime, default=datetime.now)  # 更新时间
    recorder_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)  # 记录人ID
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


# --------------------------------------------


# 用户会话表

class UserSession(db.Model):
    __tablename__ = 'user_sessions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    login_time = db.Column(db.DateTime, nullable=False)
    logout_time = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    last_activity_time = db.Column(db.DateTime, nullable=False)
    session_duration = db.Column(db.Integer)
    user_agent = db.Column(db.String(255))
    ip_address = db.Column(db.String(50))

    user = db.relationship('User', backref=db.backref('sessions', lazy='dynamic', passive_deletes=True))

    def __init__(self, user_id, ip_address=None, user_agent=None):
        self.user_id = user_id
        self.login_time = datetime.now()
        self.last_activity_time = datetime.now()
        self.is_active = True
        self.ip_address = ip_address
        self.user_agent = user_agent

    def end_session(self):
        """结束会话"""
        current_time = datetime.now()
        self.is_active = False
        self.logout_time = current_time
        if self.login_time:
            self.session_duration = int((current_time - self.login_time).total_seconds())


# 用户活动日志表
class UserActivityLog(db.Model):
    __tablename__ = 'user_activity_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    action_type = db.Column(db.String(50), nullable=False)  # 登录、注销、建项目等
    action_detail = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.now)
    resource_type = db.Column(db.String(50))  # project, task, file等
    resource_id = db.Column(db.Integer)  # 资源ID
    status_code = db.Column(db.Integer)  # HTTP状态码
    request_method = db.Column(db.String(10))  # GET, POST等
    endpoint = db.Column(db.String(255))  # API端点
    # 新增字段
    resource_type = db.Column(db.String(50))  # 例如：'project', 'task', 'file'
    resource_id = db.Column(db.Integer)
    status_code = db.Column(db.Integer)  # HTTP 状态码
    request_method = db.Column(db.String(10))  # GET, POST, PUT, DELETE 等
    endpoint = db.Column(db.String(100))  # Flask 端点名称
    request_path = db.Column(db.String(255))  # 请求路径

    # 建立与User模型的关系
    user = db.relationship('User',
                           backref=db.backref('activity_logs',
                                              lazy='dynamic',
                                              passive_deletes=True))

    def __init__(self, user_id, action_type, action_detail=None, ip_address=None,
                 resource_type=None, resource_id=None, status_code=None,
                 request_method=None, endpoint=None, request_path=None):
        self.user_id = user_id
        self.action_type = action_type
        self.action_detail = action_detail
        self.ip_address = ip_address
        self.timestamp = datetime.now()
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.status_code = status_code
        self.request_method = request_method
        self.endpoint = endpoint
        self.request_path = request_path

    @property
    def formatted_timestamp(self):
        return datetime.strptime(self.timestamp, '%Y-%m-%d %H:%M:%S')

    # 快速创建活动日志的类方法
    @classmethod
    def log_activity(cls, user_id, action_type, **kwargs):

        log = cls(user_id=user_id, action_type=action_type, **kwargs)
        db.session.add(log)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"错误记录活动： {str(e)}")


# ----------------公告板模型----------------
class Announcement(db.Model):
    __tablename__ = 'announcements'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    is_active = db.Column(db.Boolean, default=True)  # 用于软删除
    priority = db.Column(db.Integer, default=0)  # 优先级：0=普通，1=重要，2=紧急

    # 关系
    creator = db.relationship('User', backref=db.backref('announcements', lazy='dynamic'))
    read_status = db.relationship('AnnouncementReadStatus', back_populates='announcement', cascade='all, delete-orphan')


# 公告阅读状态表
class AnnouncementReadStatus(db.Model):
    __tablename__ = 'announcement_read_status'

    id = db.Column(db.Integer, primary_key=True)
    announcement_id = db.Column(db.Integer, db.ForeignKey('announcements.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime, nullable=True)

    # 关系
    announcement = db.relationship('Announcement', back_populates='read_status')
    user = db.relationship('User', backref=db.backref('announcement_reads', lazy='dynamic'))

    # 联合唯一索引确保每个用户对每个公告只有一个阅读状态
    __table_args__ = (
        db.UniqueConstraint('announcement_id', 'user_id', name='_announcement_user_uc'),
    )


# 公告附件表
class AnnouncementAttachment(db.Model):
    __tablename__ = 'announcement_attachments'

    id = db.Column(db.Integer, primary_key=True)
    announcement_id = db.Column(db.Integer, db.ForeignKey('announcements.id', ondelete='CASCADE'), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)  # 大小（以字节为单位）
    file_type = db.Column(db.String(100))
    uploaded_at = db.Column(db.DateTime, default=datetime.now)

    # 与公告的关系
    announcement = db.relationship('Announcement', backref=db.backref('attachments', cascade='all, delete-orphan'))


# -----------------------------------------------------------------------------------------

class Training(db.Model):
    __tablename__ = 'trainings'

    id = db.Column(db.Integer, primary_key=True)  # 训练ID
    trainer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # 训练师ID
    training_month = db.Column(db.String(7), nullable=False)  # 格式: "2024-01"
    title = db.Column(db.String(100), nullable=False)  # 训练标题
    description = db.Column(db.Text)  # 训练描述
    status = db.Column(db.String(20), nullable=False)  # pending, completed
    material_path = db.Column(db.String(255))  # 训练材料文件路径
    upload_time = db.Column(db.DateTime)
    create_time = db.Column(db.DateTime, default=datetime.now)
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # 关系
    trainer = db.relationship('User', backref='trainings')
    comments = db.relationship('Comment', backref='training', lazy='dynamic')


# 评论表
class Comment(db.Model):
    __tablename__ = 'comments'

    id = db.Column(db.Integer, primary_key=True)
    training_id = db.Column(db.Integer, db.ForeignKey('trainings.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    create_time = db.Column(db.DateTime, default=datetime.now)
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # 关系
    user = db.relationship('User', backref='comments')
    replies = db.relationship('Reply', backref='comment', lazy='dynamic')


class Reply(db.Model):
    __tablename__ = 'replies'

    id = db.Column(db.Integer, primary_key=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('comments.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    create_time = db.Column(db.DateTime, default=datetime.now)
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # 关系
    user = db.relationship('User', backref='replies')

    # -----------------------------------------------------------------------------------------


# AI API 表
class AIApi(db.Model):
    __tablename__ = 'ai_api'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    ai_model = db.Column(db.String(50))
    api_key = db.Column(db.String(255), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # 关系
    user = db.relationship('User', backref=db.backref('ai_apis', lazy='dynamic', passive_deletes=True))


# AI 会话表
class AIConversation(db.Model):
    __tablename__ = 'ai_conversations'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    is_archived = db.Column(db.Boolean, default=False)

    # 关系
    user = db.relationship('User', backref=db.backref('ai_conversations', lazy='dynamic', passive_deletes=True))
    messages = db.relationship('AIMessage', backref='conversation', lazy='dynamic', cascade='all, delete-orphan')
    tags = db.relationship('AITag', secondary='ai_conversation_tags',
                           backref=db.backref('conversations', lazy='dynamic'))


# AI 消息表
class AIMessage(db.Model):
    __tablename__ = 'ai_messages'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('ai_conversations.id', ondelete='CASCADE'),
                                nullable=False)
    content = db.Column(db.Text, nullable=False)
    role = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    tokens_used = db.Column(db.Integer, default=0)
    model_version = db.Column(db.String(50))

    # 反馈关系
    feedback = db.relationship('AIMessageFeedback', backref='message', lazy='dynamic', cascade='all, delete-orphan')

    # 验证 role 字段的值
    __table_args__ = (
        db.CheckConstraint("role IN ('user', 'assistant', 'system')", name='check_role'),
    )


# AI 标签表
class AITag(db.Model):
    __tablename__ = 'ai_tags'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)


# AI 会话-标签关联表
class AIConversationTag(db.Model):
    __tablename__ = 'ai_conversation_tags'

    conversation_id = db.Column(db.Integer, db.ForeignKey('ai_conversations.id', ondelete='CASCADE'),
                                primary_key=True)
    tag_id = db.Column(db.Integer, db.ForeignKey('ai_tags.id', ondelete='CASCADE'), primary_key=True)


# AI 消息反馈表
class AIMessageFeedback(db.Model):
    __tablename__ = 'ai_message_feedback'

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('ai_messages.id', ondelete='CASCADE'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1 表示点赞，-1 表示踩
    feedback_text = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)

    # 验证 rating 字段的值
    __table_args__ = (
        db.CheckConstraint("rating IN (1, -1)", name='check_rating'),
    )


# 创建索引
db.Index('idx_ai_messages_conversation_id', AIMessage.conversation_id)
db.Index('idx_ai_conversations_user_id', AIConversation.user_id)
db.Index('idx_ai_conversations_updated_at', AIConversation.updated_at)
db.Index('idx_ai_message_feedback_message_id', AIMessageFeedback.message_id)


# --------------
# [新增] 知识库主表
class KnowledgeBase(db.Model):
    __tablename__ = 'knowledge_bases'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)  # 知识库名称，必须唯一
    description = db.Column(db.Text, nullable=True)  # 描述信息
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    # --- 关系定义 ---
    # 一个知识库可以包含多个根节点
    nodes = db.relationship('KnowledgeBaseNode', back_populates='knowledge_base', cascade='all, delete-orphan')
    creator = db.relationship('User', backref='created_knowledge_bases')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'created_by_id': self.created_by_id,
            'created_at': self.created_at.isoformat()
        }


# [修改] 知识库节点模型
class KnowledgeBaseNode(db.Model):
    __tablename__ = 'knowledge_base_nodes'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)

    # --- 核心：自引用外键 ---
    parent_id = db.Column(db.Integer, db.ForeignKey('knowledge_base_nodes.id', ondelete='CASCADE'), nullable=True)

    # --- 新增外键，关联到知识库主表 ---
    kb_id = db.Column(db.Integer, db.ForeignKey('knowledge_bases.id'), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # --- 关系定义 ---
    parent = db.relationship('KnowledgeBaseNode', remote_side=[id],
                             backref=db.backref('children', lazy='dynamic', cascade='all, delete-orphan'))
    files = db.relationship('KnowledgeBaseFile', back_populates='node', cascade='all, delete-orphan')

    # 新增关系，反向引用到知识库主表
    knowledge_base = db.relationship('KnowledgeBase', back_populates='nodes')

    def to_dict(self, include_children=True):
        node_dict = {
            'id': self.id,
            'kb_id': self.kb_id,  # 返回所属知识库ID
            'name': self.name,
            'description': self.description,
            'parent_id': self.parent_id,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'files': [file.to_dict() for file in self.files]
        }
        if include_children:
            # 查询时需要注意过滤kb_id
            children_query = self.children.filter(KnowledgeBaseNode.kb_id == self.kb_id)
            node_dict['children'] = [child.to_dict() for child in children_query]
        else:
            node_dict['children'] = []
        return node_dict


# 知识库文件模型
class KnowledgeBaseFile(db.Model):
    __tablename__ = 'knowledge_base_files'
    id = db.Column(db.Integer, primary_key=True)
    node_id = db.Column(db.Integer, db.ForeignKey('knowledge_base_nodes.id'), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(100))
    upload_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    upload_date = db.Column(db.DateTime, default=datetime.now)
    node = db.relationship('KnowledgeBaseNode', back_populates='files')
    upload_user = db.relationship('User', backref='knowledge_base_files')

    def to_dict(self):
        return {
            'id': self.id,
            'node_id': self.node_id,
            'original_name': self.original_name,
            'file_path': self.file_path,
            'file_type': self.file_type,
            'upload_user_id': self.upload_user_id,
            'upload_date': self.upload_date.isoformat()
        }
