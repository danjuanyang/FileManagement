# routes/leader.py
from flask import Blueprint, request, jsonify
from flask_cors import CORS

from app import app
from modles import db, Project, ProjectFile, User
from datetime import datetime
from werkzeug.utils import secure_filename
import os

leader_bp = Blueprint('leader', __name__)

# 允许所有跨域
CORS(app)
# 获取所有项目列表
@leader_bp.route('/projects', methods=['GET'])
def get_projects():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    search = request.args.get('search', '')

    query = Project.query
    if search:
        query = query.filter(Project.name.ilike(f'%{search}%'))

    projects = query.paginate(page=page, per_page=per_page)

    return jsonify({
        'projects': [{
            'id': p.id,
            'name': p.name,
            'description': p.description,
            'employee': p.employee.username if p.employee else None,
            'start_date': p.start_date.isoformat(),
            'deadline': p.deadline.isoformat(),
            'progress': p.progress,
            'status': p.status
        } for p in projects.items],
        'total': projects.total,
        'pages': projects.pages,
        'current_page': page
    })


# 创建新项目
@leader_bp.route('/projects', methods=['POST'])
def create_project():
    data = request.get_json()

    project = Project(
        name=data['name'],
        description=data['description'],
        employee_id=data['employee_id'],
        start_date=datetime.fromisoformat(data['start_date']),
        deadline=datetime.fromisoformat(data['deadline']),
        status='pending'
    )

    db.session.add(project)
    db.session.commit()

    return jsonify({
        'message': '项目创建成功',
        'project_id': project.id
    }), 201


# 更新项目
@leader_bp.route('/projects/<int:project_id>', methods=['PUT'])
def update_project(project_id):
    project = Project.query.get_or_404(project_id)
    data = request.get_json()

    for key, value in data.items():
        if hasattr(project, key):
            if key in ['start_date', 'deadline']:
                value = datetime.fromisoformat(value)
            setattr(project, key, value)

    db.session.commit()
    return jsonify({'message': '项目更新成功'})


# 获取项目文件列表
@leader_bp.route('/projects/<int:project_id>/files', methods=['GET'])
def get_project_files(project_id):
    files = ProjectFile.query.filter_by(project_id=project_id).all()
    return jsonify({
        'files': [{
            'id': f.id,
            'file_name': f.file_name,
            'file_type': f.file_type,
            'file_url': f.file_url,
            'file_size': f.file_size,
            'upload_user': f.upload_user.username,
            'upload_date': f.upload_date.isoformat()
        } for f in files]
    })


# 搜索文件
@leader_bp.route('/files/search', methods=['GET'])
def search_files():
    keyword = request.args.get('keyword', '')
    files = ProjectFile.query.filter(ProjectFile.file_name.ilike(f'%{keyword}%')).all()
    return jsonify({
        'files': [{
            'id': f.id,
            'file_name': f.file_name,
            'file_type': f.file_type,
            'file_url': f.file_url,
            'project_name': f.project.name,
            'upload_user': f.upload_user.username
        } for f in files]
    })


# 获取所有员工列表
@leader_bp.route('/employees', methods=['GET'])
def get_employees():
    employees = User.query.filter_by(role=2).all()
    return jsonify({
        'employees': [{
            'id': e.id,
            'username': e.username
        } for e in employees]
    })