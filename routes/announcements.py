# routes/announcements.py
from flask import Blueprint, request, jsonify
from flask_cors import CORS
from datetime import datetime
from models import db, Announcement, AnnouncementReadStatus, User
from routes.employees import token_required
from utils.activity_tracking import track_activity

announcement_bp = Blueprint('announcement', __name__)
CORS(announcement_bp)


# 管理员创建公告
@announcement_bp.route('/announcements', methods=['POST'])
@track_activity
@token_required
def create_announcement(current_user):
    if current_user.role != 1:  # 检查是否是管理员
        return jsonify({'error': '权限不足'}), 403

    try:
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
        db.session.flush()  # 获取announcement.id

        # 为所有用户创建未读状态
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
                'priority': announcement.priority
            }
        }), 201

    except Exception as e:
        db.session.rollback()
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

        return jsonify({
            'announcements': [{
                'id': ann.id,
                'title': ann.title,
                'content': ann.content,
                'created_by': ann.creator.username if ann.creator else None,
                'created_at': ann.created_at.isoformat(),
                'priority': ann.priority,
                'is_read': read_status.get(ann.id, False),
                'is_active': ann.is_active
            } for ann in announcements.items],
            'total': announcements.total,
            'pages': announcements.pages,
            'current_page': page
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
        data = request.get_json()

        # 记录是否有内容变更
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

        # 更新状态字段（不触发重置阅读状态）
        if 'is_active' in data:
            announcement.is_active = bool(data['is_active'])

        # 如果内容发生变化，重置所有用户的阅读状态
        if content_changed:
            read_statuses = AnnouncementReadStatus.query.filter_by(announcement_id=announcement_id).all()
            for status in read_statuses:
                status.is_read = False
                status.read_at = None

        # 提交更改
        db.session.commit()
        db.session.refresh(announcement)

        return jsonify({
            'message': '公告更新成功',
            'announcement': {
                'id': announcement.id,
                'title': announcement.title,
                'content': announcement.content,
                'priority': announcement.priority,
                'is_active': bool(announcement.is_active),
                'created_at': announcement.created_at.isoformat() if announcement.created_at else None
            }
        })

    except Exception as e:
        print(f"更新公告时出错：{str(e)}")
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
