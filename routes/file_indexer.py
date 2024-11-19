# file_indexer.py
import os
from PyPDF2 import PdfReader
from docx import Document
import textract
import magic


class FileContentExtractor:
    @staticmethod
    def extract_content(file_path):
        """
        根据文件类型提取文本内容
        """
        try:
            # 检测文件类型
            mime = magic.Magic(mime=True)
            file_type = mime.from_file(file_path)

            # 根据文件类型选择不同的提取方法
            if file_type == 'application/pdf':
                return FileContentExtractor._extract_pdf(file_path)
            elif file_type in ['application/msword',
                               'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
                return FileContentExtractor._extract_docx(file_path)
            elif file_type == 'text/plain':
                return FileContentExtractor._extract_txt(file_path)
            else:
                # 使用textract尝试提取其他格式
                return textract.process(file_path).decode('utf-8')

        except Exception as e:
            print(f"内容提取错误: {file_path}: {str(e)}")
            return None

    @staticmethod
    def _extract_pdf(file_path):
        with open(file_path, 'rb') as file:
            reader = PdfReader(file)
            return ' '.join(page.extract_text() for page in reader.pages)

    @staticmethod
    def _extract_docx(file_path):
        doc = Document(file_path)
        return ' '.join(paragraph.text for paragraph in doc.paragraphs)

    @staticmethod
    def _extract_txt(file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()