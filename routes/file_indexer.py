# file_indexer.py
import os
import io
from docx import Document
import PyPDF2
import openpyxl
import chardet
import sqlite3
from flask import current_app

from models import db, ProjectFile, FileContent


def detect_file_encoding(file_path):
    """检测文件编码"""
    with open(file_path, 'rb') as file:
        raw_data = file.read()
        result = chardet.detect(raw_data)
        return result['encoding']


def extract_text_from_docx(file_path):
    """提取Word文档内容"""
    try:
        doc = Document(file_path)
        full_text = []
        for paragraph in doc.paragraphs:
            full_text.append(paragraph.text)
        return '\n'.join(full_text)
    except Exception as e:
        print(f"Extract docx error: {str(e)}")
        return None


def extract_text_from_pdf(file_path):
    """提取PDF文档内容"""
    try:
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = []
            for page in reader.pages:
                text.append(page.extract_text())
            return '\n'.join(text)
    except Exception as e:
        print(f"Extract PDF error: {str(e)}")
        return None


def extract_text_from_excel(file_path):
    """提取Excel文档内容"""
    try:
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        text = []
        for sheet in wb.sheetnames:
            ws = wb[sheet]
            for row in ws.rows:
                row_text = ' '.join(str(cell.value) for cell in row if cell.value is not None)
                if row_text.strip():
                    text.append(row_text)
        return '\n'.join(text)
    except Exception as e:
        print(f"Extract Excel error: {str(e)}")
        return None


def extract_text_from_txt(file_path):
    """提取文本文件内容"""
    try:
        encoding = detect_file_encoding(file_path)
        with open(file_path, 'r', encoding=encoding) as file:
            return file.read()
    except Exception as e:
        print(f"Extract txt error: {str(e)}")
        return None


def create_file_index(file_path, file_type):
    """创建文件索引"""
    extractors = {
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': extract_text_from_docx,
        'application/pdf': extract_text_from_pdf,
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': extract_text_from_excel,
        'text/plain': extract_text_from_txt
    }

    # 根据文件类型选择提取器
    extractor = extractors.get(file_type)
    if not extractor:
        print(f"Unsupported file type: {file_type}")
        return None

    try:
        # 提取文件内容
        extracted_text = extractor(file_path)
        if extracted_text:
            # 处理提取的文本，移除多余的空白字符
            processed_text = ' '.join(extracted_text.split())
            return processed_text
        return None
    except Exception as e:
        print(f"Index creation error: {str(e)}")
        return None


def update_file_index(project_file_id, file_path, file_type):
    """更新文件索引"""
    try:
        # 提取文件内容
        extracted_text = create_file_index(file_path, file_type)

        if extracted_text:
            # 获取或创建FileContent记录
            file_content = FileContent.query.filter_by(file_id=project_file_id).first()
            if not file_content:
                file_content = FileContent(file_id=project_file_id)

            file_content.content = extracted_text

            # 更新ProjectFile的text_extracted标志
            project_file = ProjectFile.query.get(project_file_id)
            project_file.text_extracted = True

            # 保存更改
            db.session.add(file_content)
            db.session.add(project_file)
            db.session.commit()

            return True
    except Exception as e:
        print(f"索引更新错误： {str(e)}")
        db.session.rollback()
        return False


# 文件类型映射
MIME_TYPE_MAPPING = {
    'doc': 'application/msword',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'pdf': 'application/pdf',
    'xls': 'application/vnd.ms-excel',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'txt': 'text/plain'
}


def get_mime_type(filename):
    """根据文件扩展名获取MIME类型"""
    ext = filename.rsplit('.', 1)[-1].lower()
    return MIME_TYPE_MAPPING.get(ext)