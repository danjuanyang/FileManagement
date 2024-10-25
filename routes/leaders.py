# routes/leaders.py
from flask import Blueprint, request, jsonify
from flask_cors import CORS
from models import db, Project, ProjectFile, User
from datetime import datetime

leader_bp = Blueprint('leader', __name__)
CORS(leader_bp)


@leader_bp.route('/projects', methods=['GET'])
def get_projects():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    search = request.args.get('search', '')

    query = Project.query
    if search:
        query = query.filter(Project.name.ilike(f'%{search}%'))

    projects = query.paginate(page=page, per_page=per_page)

    def format_date(date):
        return date.strftime('%Y-%m-%d') if date else None

    return jsonify({
        'projects': [{
            'id': p.id,
            'name': p.name,
            'description': p.description,
            'employee': p.employee.username if p.employee else None,
            'start_date': format_date(p.start_date),
            'deadline': format_date(p.deadline),
            'progress': p.progress,
            'status': p.status
        } for p in projects.items],
        'total': projects.total,
        'pages': projects.pages,
        'current_page': page
    })



# 创建项目
@leader_bp.route('/projects', methods=['POST'])
def create_project():
    data = request.get_json()

    # 验证员工是否存在
    if 'employee_id' in data:
        employee = User.query.get(data['employee_id'])
        if not employee:
            return jsonify({'error': '员工不存在'}), 400

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

    # 明确定义可更新的字段及其处理方式
    update_handlers = {
        'name': lambda x: x,
        'description': lambda x: x,
        'status': lambda x: x,
        'progress': lambda x: x,
        'start_date': lambda x: datetime.fromisoformat(x),
        'deadline': lambda x: datetime.fromisoformat(x),
        'employee': lambda x: User.query.get(x) if x else None,
        'employee_id': lambda x: User.query.get(x) if x else None
    }

    try:
        for key, value in data.items():
            if key in update_handlers:
                if key == 'employee' or key == 'employee_id':
                    if value:
                        employee = User.query.get(value)
                        if employee is None:
                            return jsonify({'error': f'员工ID {value} 不存在'}), 400
                        project.employee = employee
                else:
                    processed_value = update_handlers[key](value)
                    setattr(project, key, processed_value)

        db.session.commit()
        return jsonify({
            'message': '项目更新成功',
            'project': {
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'employee': project.employee.username if project.employee else None,
                'start_date': project.start_date.isoformat() if project.start_date else None,
                'deadline': project.deadline.isoformat() if project.deadline else None,
                'progress': project.progress,
                'status': project.status
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500



# 查看项目文件
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
