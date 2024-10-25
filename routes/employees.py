

# router/employees.py
from datetime import datetime

import jwt
from flask import Blueprint, request, jsonify
from flask_cors import CORS

from config import app
from models import db, Project, ProjectFile
from auth import get_employee_id

employee_bp = Blueprint('employee', __name__)
CORS(employee_bp)  # 为此蓝图启用 CORS


# 用于解码 JWT 的辅助函数
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

    return jsonify({'message': 'Project updated successfully'})


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
