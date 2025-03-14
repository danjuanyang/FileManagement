# routes/announcements.py
import os
from flask import Blueprint, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime

from werkzeug.utils import secure_filename

from models import db, Announcement, AnnouncementReadStatus, User, AnnouncementAttachment
from routes.employees import token_required
from utils.activity_tracking import track_activity

announcement_bp = Blueprint('announcement', __name__)
CORS(announcement_bp)

# 为文件上传添加配置
UPLOAD_FOLDER = 'uploads/announcements'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'zip', 'rar', 'png', 'jpg', 'jpeg',
                      'gif'}

# 如果不存在，则创建上传目录
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# 管理员创建公告
@announcement_bp.route('/announcements', methods=['POST'])
@track_activity
@token_required
def create_announcement(current_user):
    if current_user.role != 1:  # Check if admin
        return jsonify({'error': '权限不足'}), 403

    try:
        # 检查请求是否包含表单数据或 JSON
        if request.content_type and 'multipart/form-data' in request.content_type:
            title = request.form.get('title')
            content = request.form.get('content')
            priority = request.form.get('priority', 0, type=int)

            if not title or not content:
                return jsonify({'error': '缺少必要字段'}), 400

            announcement = Announcement(
                title=title,
                content=content,
                created_by=current_user.id,
                priority=priority
            )
        else:
            data = request.get_json()

            if not all(k in data for k in ('title', 'content')):
                return jsonify({'error': '缺少必要字段'}), 400

            announcement = Announcement(
                title=data['title'],
                content=data['content'],
                created_by=current_user.id,
                priority=data.get('priority', 0)
            )

        db.session.add(announcement)
        db.session.flush()  # 获取 announcement.id

        # 处理文件上传
        files = request.files.getlist('attachments')
        attachments = []

        for file in files:
            if file and file.filename and allowed_file(file.filename):
                # 保持原始文件名不变
                original_filename = file.filename

                # 为防止文件名冲突，创建一个唯一的存储文件名
                file_ext = os.path.splitext(original_filename)[1] if '.' in original_filename else ''
                unique_id = f"{announcement.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                stored_filename = f"{unique_id}{file_ext}"
                file_path = os.path.join(UPLOAD_FOLDER, stored_filename)

                # 保存文件
                file.save(file_path)

                # 创建附件记录 - 使用原始文件名
                attachment = AnnouncementAttachment(
                    announcement_id=announcement.id,
                    original_filename=original_filename,  # 安全处理后的原始文件名
                    stored_filename=stored_filename,  # 存储用的唯一文件名
                    file_size=os.path.getsize(file_path),
                    file_type=file.content_type if hasattr(file, 'content_type') else None
                )
                db.session.add(attachment)

                # 在响应中使用原始文件名，保持与数据库一致
                attachments.append({
                    'filename': original_filename,  # 使用安全处理后的原始文件名
                    'size': attachment.file_size
                })

        # 为所有用户创建读取状态
        users = User.query.all()
        for user in users:
            read_status = AnnouncementReadStatus(
                announcement_id=announcement.id,
                user_id=user.id
            )
            db.session.add(read_status)

        db.session.commit()

        return jsonify({
            'message': '公告创建成功',
            'announcement': {
                'id': announcement.id,
                'title': announcement.title,
                'content': announcement.content,
                'created_at': announcement.created_at.isoformat(),
                'priority': announcement.priority,
                'attachments': attachments
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# 下载附件
# 下载附件
@announcement_bp.route('/announcements/<int:announcement_id>/attachments/<int:attachment_id>', methods=['GET'])
@track_activity
@token_required
def download_attachment(current_user, announcement_id, attachment_id):
    try:
        # 获取附件
        attachment = AnnouncementAttachment.query.filter_by(
            id=attachment_id,
            announcement_id=announcement_id
        ).first_or_404()

        # 将公告标记为已读（如果尚未）
        read_status = AnnouncementReadStatus.query.filter_by(
            announcement_id=announcement_id,
            user_id=current_user.id
        ).first()

        if read_status and not read_status.is_read:
            read_status.is_read = True
            read_status.read_at = datetime.now()
            db.session.commit()

        # 修复：使用 werkzeug 的安全文件名确保文件名与标头兼容
        # 和 URL 对 Content-Disposition 标头的文件名进行编码
        from urllib.parse import quote
        encoded_filename = quote(attachment.original_filename)

        # 明确设置响应头以确保文件名正确传递
        response = send_from_directory(
            UPLOAD_FOLDER,
            attachment.stored_filename,
            as_attachment=True,
            download_name=attachment.original_filename
        )

        # 简化的 Content-Disposition 标头与 HTTP 1.1 规范兼容
        response.headers['Content-Disposition'] = f"attachment; filename={encoded_filename}"

        return response

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# 获取公告列表（支持分页和筛选）
@announcement_bp.route('/announcements', methods=['GET'])
@track_activity
@token_required
def get_announcements(current_user):
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        show_inactive = request.args.get('show_inactive', 'false').lower() == 'true'

        query = Announcement.query

        # 只有管理员可以看到未激活的公告
        if not show_inactive or current_user.role != 1:
            query = query.filter_by(is_active=True)

        announcements = query.order_by(
            Announcement.priority.desc(),
            Announcement.created_at.desc()
        ).paginate(page=page, per_page=per_page)

        # 获取当前用户的阅读状态
        read_status = {
            status.announcement_id: status.is_read
            for status in AnnouncementReadStatus.query.filter_by(user_id=current_user.id).all()
        }

        result = []
        for ann in announcements.items:
            # 获取公告的附件信息
            attachments = [{
                'id': attachment.id,
                'filename': attachment.original_filename,
                'size': attachment.file_size,
                'uploaded_at': attachment.uploaded_at.isoformat() if attachment.uploaded_at else None
            } for attachment in ann.attachments]

            # 构建公告对象，包含附件信息
            result.append({
                'id': ann.id,
                'title': ann.title,
                'content': ann.content,
                'created_by': ann.creator.username if ann.creator else None,
                'created_at': ann.created_at.isoformat(),
                'updated_at': ann.updated_at.isoformat() if ann.updated_at else None,
                'priority': ann.priority,
                'is_read': read_status.get(ann.id, False),
                'is_active': ann.is_active,
                'attachments': attachments
            })

        return jsonify({
            'announcements': result,
            'total': announcements.total,
            'pages': announcements.pages,
            'current_page': page
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@announcement_bp.route('/announcements/<int:announcement_id>', methods=['GET'])
@track_activity
@token_required
def get_announcement(current_user, announcement_id):
    try:
        announcement = Announcement.query.get_or_404(announcement_id)

        # 检查公告是否处于活动状态，或者用户是否为管理员
        if not announcement.is_active and current_user.role != 1:
            return jsonify({'error': '公告不存在或已下线'}), 404

        # 获取当前用户的读取状态
        read_status = AnnouncementReadStatus.query.filter_by(
            announcement_id=announcement_id,
            user_id=current_user.id
        ).first()

        # 获取附件
        attachments = [{
            'id': attachment.id,
            'filename': attachment.original_filename,
            'size': attachment.file_size,
            'uploaded_at': attachment.uploaded_at.isoformat() if attachment.uploaded_at else None
        } for attachment in announcement.attachments]

        return jsonify({
            'announcement': {
                'id': announcement.id,
                'title': announcement.title,
                'content': announcement.content,
                'created_by': announcement.creator.username if announcement.creator else None,
                'created_at': announcement.created_at.isoformat(),
                'updated_at': announcement.updated_at.isoformat() if announcement.updated_at else None,
                'priority': announcement.priority,
                'is_read': read_status.is_read if read_status else False,
                'is_active': announcement.is_active,
                'attachments': attachments
            }
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# 标记公告为已读/未读
@announcement_bp.route('/announcements/<int:announcement_id>/read-status', methods=['PUT'])
@track_activity
@token_required
def update_read_status(current_user, announcement_id):
    try:
        data = request.get_json()
        is_read = data.get('is_read', True)

        read_status = AnnouncementReadStatus.query.filter_by(
            announcement_id=announcement_id,
            user_id=current_user.id
        ).first()

        if not read_status:
            read_status = AnnouncementReadStatus(
                announcement_id=announcement_id,
                user_id=current_user.id
            )
            db.session.add(read_status)

        read_status.is_read = is_read
        if is_read:
            read_status.read_at = datetime.now()

        db.session.commit()

        return jsonify({
            'message': '阅读状态更新成功',
            'is_read': is_read
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# 管理员获取公告阅读状态统计
@announcement_bp.route('/announcements/<int:announcement_id>/read-statistics', methods=['GET'])
@track_activity
@token_required
def get_read_statistics(current_user, announcement_id):
    if current_user.role != 1:
        return jsonify({'error': '权限不足'}), 403

    try:
        announcement = Announcement.query.get_or_404(announcement_id)

        # 获取所有非管理员用户的阅读状态
        read_status = (AnnouncementReadStatus.query
                       .join(User)
                       .filter(AnnouncementReadStatus.announcement_id == announcement_id)
                       .all())

        # 统计非管理员用户的数量和已读数量
        user_status = [{
            'user_id': status.user_id,
            'username': status.user.username,
            'is_read': status.is_read,
            'read_at': status.read_at.isoformat() if status.read_at else None,
            'role': status.user.role  # 添加用户角色信息
        } for status in read_status]

        # 计算总数（所有用户，包括管理员）
        total_users = len(read_status)
        # 计算已读数（所有用户，包括管理员）
        read_users = sum(1 for status in read_status if status.is_read)

        return jsonify({
            'announcement_id': announcement_id,
            'title': announcement.title,
            'total_users': total_users,
            'read_users': read_users,
            'read_percentage': (read_users / total_users * 100) if total_users > 0 else 0,
            'user_status': user_status
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# 管理员编辑公告
@announcement_bp.route('/announcements/<int:announcement_id>', methods=['PUT'])
@track_activity
@token_required
def update_announcement(current_user, announcement_id):
    if current_user.role != 1:
        return jsonify({'error': '权限不足'}), 403

    try:
        announcement = Announcement.query.get_or_404(announcement_id)

        # 检查请求是否包含表单数据或 JSON
        if request.content_type and 'multipart/form-data' in request.content_type:
            title = request.form.get('title')
            content = request.form.get('content')
            priority = request.form.get('priority', type=int)
            is_active = request.form.get('is_active', type=bool)

            content_changed = False

            if title and title != announcement.title:
                announcement.title = title
                content_changed = True

            if content and content != announcement.content:
                announcement.content = content
                content_changed = True

            if priority is not None and priority != announcement.priority:
                announcement.priority = priority
                content_changed = True

            if is_active is not None:
                announcement.is_active = is_active

            # 处理文件上传
            files = request.files.getlist('attachments')
            attachments = []

            for file in files:
                if file and file.filename and allowed_file(file.filename):
                    # 保持原始文件名不变
                    original_filename = file.filename

                    # 生成唯一的存储文件名
                    file_ext = os.path.splitext(original_filename)[1] if '.' in original_filename else ''
                    unique_id = f"{announcement.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    stored_filename = f"{unique_id}{file_ext}"
                    file_path = os.path.join(UPLOAD_FOLDER, stored_filename)

                    # 保存文件
                    file.save(file_path)

                    # 创建附件记录
                    attachment = AnnouncementAttachment(
                        announcement_id=announcement.id,
                        original_filename=original_filename,  # 安全处理后的原始文件名
                        stored_filename=stored_filename,
                        file_size=os.path.getsize(file_path),
                        file_type=file.content_type if hasattr(file, 'content_type') else None
                    )
                    db.session.add(attachment)
                    attachments.append({
                        'filename': original_filename,  # 使用安全处理后的原始文件名
                        'size': attachment.file_size
                    })
                    content_changed = True
        else:
            # 处理 JSON 数据
            data = request.get_json()
            content_changed = False

            # 更新字段
            if 'title' in data and data['title'] != announcement.title:
                announcement.title = data['title']
                content_changed = True

            if 'content' in data and data['content'] != announcement.content:
                announcement.content = data['content']
                content_changed = True

            if 'priority' in data and data['priority'] != announcement.priority:
                announcement.priority = data['priority']
                content_changed = True

            # 更新状态字段（不触发读取状态重置）
            if 'is_active' in data:
                announcement.is_active = bool(data['is_active'])

        # 如果内容已更改，则重置所有用户的读取状态
        if content_changed:
            read_statuses = AnnouncementReadStatus.query.filter_by(announcement_id=announcement_id).all()
            for status in read_statuses:
                status.is_read = False
                status.read_at = None

        # 提交更改
        db.session.commit()
        db.session.refresh(announcement)

        # 获取当前附件以进行响应
        current_attachments = [{
            'id': attachment.id,
            'filename': attachment.original_filename,
            'size': attachment.file_size,
            'uploaded_at': attachment.uploaded_at.isoformat()
        } for attachment in announcement.attachments]

        return jsonify({
            'message': '公告更新成功',
            'announcement': {
                'id': announcement.id,
                'title': announcement.title,
                'content': announcement.content,
                'priority': announcement.priority,
                'is_active': bool(announcement.is_active),
                'created_at': announcement.created_at.isoformat() if announcement.created_at else None,
                'attachments': current_attachments
            }
        })

    except Exception as e:
        print(f"更新公告时出错：{str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# 删除公告附件
@announcement_bp.route('/announcements/<int:announcement_id>/attachments/<int:attachment_id>', methods=['DELETE'])
@track_activity
@token_required
def delete_attachment(current_user, announcement_id, attachment_id):
    if current_user.role != 1:
        return jsonify({'error': '权限不足'}), 403

    try:
        attachment = AnnouncementAttachment.query.filter_by(
            id=attachment_id,
            announcement_id=announcement_id
        ).first_or_404()

        # 从磁盘中删除文件
        file_path = os.path.join(UPLOAD_FOLDER, attachment.stored_filename)
        if os.path.exists(file_path):
            os.remove(file_path)

        # 从数据库中删除
        db.session.delete(attachment)
        db.session.commit()

        return jsonify({'message': '附件删除成功'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# 获取未读公告数量
@announcement_bp.route('/announcements/unread-count', methods=['GET'])
@track_activity
@token_required
def get_unread_count(current_user):
    try:
        unread_count = AnnouncementReadStatus.query.join(Announcement).filter(
            AnnouncementReadStatus.user_id == current_user.id,
            AnnouncementReadStatus.is_read == False,
            Announcement.is_active == True
        ).count()

        return jsonify({
            'unread_count': unread_count
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# 重置公告阅读状态
@announcement_bp.route('/announcements/<int:announcement_id>/reset-read-status', methods=['PUT'])
@track_activity
@token_required
def reset_read_status(current_user, announcement_id):
    try:
        # 检索特定公告和用户的读取状态
        read_status = AnnouncementReadStatus.query.filter_by(
            user_id=current_user.id,
            announcement_id=announcement_id
        ).first()

        if read_status:
            read_status.is_read = False
            read_status.read_at = None
            db.session.commit()

            return jsonify({'message': '公告阅读状态重置为未读成功'})

        return jsonify({'error': '未找到阅读状态'}), 404

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
