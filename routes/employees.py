

# router/employees.py
from datetime import datetime

import jwt
from flask import Blueprint, request, jsonify
from flask_cors import CORS

from config import app
from models import db, Project, ProjectFile, ProjectUpdate
from auth import get_employee_id

employee_bp = Blueprint('employee', __name__)
CORS(employee_bp)  # 为此蓝图启用 CORS


# 用于解码 JWT 令牌并返回员工 ID
def get_employee_id():
    token = request.headers.get('Authorization').split()[1]
    data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
    return data['user_id']

#工程查看和编辑路线
@employee_bp.route('/projects', methods=['GET'])
def get_assigned_projects():
    employee_id = get_employee_id()
    projects = Project.query.filter_by(employee_id=employee_id).all()
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'description': p.description,
        'start_date': p.start_date.strftime('%Y-%m-%d'),
        'deadline': p.deadline.strftime('%Y-%m-%d'),
        'progress': p.progress,
        'status': p.status
    } for p in projects])


@employee_bp.route('/projects/<int:project_id>', methods=['PUT'])
def update_project_plan(project_id):
    project = Project.query.get_or_404(project_id)
    data = request.get_json()

    project.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d')
    project.deadline = datetime.strptime(data['deadline'], '%Y-%m-%d')
    db.session.commit()

    return jsonify({'message': '项目更新成功'})


# 文件上传、编辑和删除
@employee_bp.route('/projects/<int:project_id>/files', methods=['POST'])
def upload_file(project_id):
    file = request.files['file']
    employee_id = request.form['employee_id']

    project_file = ProjectFile(
        project_id=project_id,
        file_name=file.filename,
        file_type=file.content_type,
        file_url=f'/uploads/{file.filename}',
        upload_user_id=employee_id,
        upload_date=datetime.now()
    )
    db.session.add(project_file)
    db.session.commit()
    file.save(f'uploads/{file.filename}')

    return jsonify({'message': 'File uploaded successfully'})



# 获取文件并显示
@employee_bp.route('/projects/<int:project_id>/files/<int:file_id>', methods=['DELETE'])
def delete_file(project_id, file_id):
    project_file = ProjectFile.query.get_or_404(file_id)
    db.session.delete(project_file)
    db.session.commit()
    return jsonify({'message': 'File deleted successfully'})


# 进度跟踪
@employee_bp.route('/projects/<int:project_id>/progress', methods=['PUT'])
def update_progress(project_id):
    project = Project.query.get_or_404(project_id)
    data = request.get_json()
    project.progress = data['progress']
    db.session.commit()
    return jsonify({'message': 'Progress updated successfully'})


# 文件搜索
@employee_bp.route('/files/search', methods=['GET'])
def search_files():
    keyword = request.args.get('keyword', '')
    employee_id = request.args.get('employee_id', type=int)
    files = ProjectFile.query.filter(ProjectFile.file_name.ilike(f'%{keyword}%'),
                                     ProjectFile.upload_user_id == employee_id).all()
    return jsonify([{
        'id': f.id,
        'file_name': f.file_name,
        'file_type': f.file_type,
        'file_url': f.file_url,
        'project_name': f.project.name
    } for f in files])


# 获取项目进度以供显示
@employee_bp.route('/projects/<int:project_id>/timeline', methods=['GET'])
def get_project_timeline(project_id):
    project = Project.query.get_or_404(project_id)
    return jsonify({
        'start_date': project.start_date.strftime('%Y-%m-%d'),
        'deadline': project.deadline.strftime('%Y-%m-%d'),
        'progress': project.progress
    })


# 截止日期提醒
@employee_bp.route('/projects/reminders', methods=['GET'])
def get_reminders():
    employee_id = request.args.get('employee_id', type=int)
    projects = Project.query.filter_by(employee_id=employee_id).all()
    reminders = []

    for project in projects:
        if project.deadline and project.deadline.date() < datetime.now().date():
            reminders.append({
                'project_id': project.id,
                'message': f'Project {project.name} is past the deadline!'
            })
        elif project.deadline and (project.deadline - datetime.now()).days < 7:
            reminders.append({
                'project_id': project.id,
                'message': f'Project {project.name} is approaching the deadline!'
            })

    return jsonify(reminders)


# 获取项目更新
# @employee_bp.route('/projects/<int:project_id>/updates', methods=['GET'])
# def get_project_updates(project_id):
#     project = Project.query.get_or_404(project_id)
#     updates = ProjectUpdate.query.filter_by(project_id=project_id).all()
#
#     return jsonify({
#         'updates': [{
#             'id': update.id,
#             'progress': update.progress,
#             'description': update.description,
#             'created_at': update.created_at.isoformat(),
#             'type': update.type
#         } for update in updates]
#     })

# @employee_bp.route('/projects/<int:project_id>/updates', methods=['GET'])
# def get_project_updates(project_id):
#     project = Project.query.get_or_404(project_id)
#     updates = ProjectUpdate.query.filter_by(project_id=project_id).order_by(ProjectUpdate.created_at.desc()).all()
#
#     return jsonify({
#         'id': project.id,
#         'name': project.name,
#         'description': project.description,
#         'start_date': project.start_date.strftime('%Y-%m-%d'),
#         'deadline': project.deadline.strftime('%Y-%m-%d'),
#         'progress': project.progress,
#         'status': project.status,
#         'updates': [{
#             'id': update.id,
#             'progress': update.progress,
#             'description': update.description,
#             'created_at': update.created_at.isoformat(),
#             'type': update.type
#         } for update in updates]
#     })


@employee_bp.route('/projects/<int:project_id>/updates', methods=['GET'])
def get_project_updates(project_id):
    try:
        project = Project.query.get_or_404(project_id)
        updates = ProjectUpdate.query.filter_by(project_id=project_id) \
            .order_by(ProjectUpdate.created_at.desc()).all()

        return jsonify({
            'updates': [{
                'id': update.id,
                'progress': update.progress,
                'description': update.description,
                'created_at': update.created_at.isoformat(),
                'type': update.type
            } for update in updates]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# 更新项目进度
@employee_bp.route('/projects/<int:project_id>/progress', methods=['POST'])
def update_project_progress(project_id):
    project = Project.query.get_or_404(project_id)
    data = request.get_json()

    if 'progress' not in data or 'description' not in data:
        return jsonify({'error': '无效的负载'}), 400

    new_update = ProjectUpdate(
        project_id=project_id,
        progress=data['progress'],
        description=data['description'],
        created_at=datetime.utcnow(),
        type='progress'
    )

    project.progress = data['progress']

    db.session.add(new_update)
    db.session.commit()

    return jsonify({
        'message': '已成功更新进度',
        # 返回所有更新
        'update_id': new_update.id
    })