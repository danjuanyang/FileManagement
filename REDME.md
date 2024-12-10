# 后端

## 开发和部署需要修改`filemanagement.py`和`config.py`群晖配置

### filemanagement.py

```python
# 群晖路径
python_dir  = '/volume1/web/FileManagementFolder/db'
UPLOAD_FOLDER = '/volume1/web/FileManagementFolder/uploads'
ALLOWED_EXTENSIONS = {'doc', 'docx', 'pdf', 'xls', 'xlsx', 'txt', 'zip', 'rar'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
BASE_UPLOAD_FOLDER = os.path.join(python_dir, 'uploads')  # 基础上传目录
```

### config.py

```python
# 群晖路径
    # 获取Python解释器所在目录
    python_dir = '/volume1/web/FileManagementFolder/db'
    # # 构建数据库文件路径
    db_path = os.path.join(python_dir, 'project.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'

```

