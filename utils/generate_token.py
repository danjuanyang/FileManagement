import jwt
import datetime

def generate_permanent_token():
    """
    生成一个永不过期的JWT，用于内部服务认证。
    """
    # !!! 警告 !!!
    # 下方的 SECRET_KEY 必须和 Flask 应用中 config.py 文件里的 'SECRET_KEY' 完全一致。
    # 从 config.py 文件获取，这个值是 '9888898888'。
    SECRET_KEY = '9888898888'

    # !!! 重要 !!!
    # 在此处填入一个具有管理员权限的用户ID。
    # Email_reminder.py 脚本将使用此用户的身份来请求API。
    USER_ID_FOR_SCRIPT = 1  # <--- 修改这里为您系统中的管理员用户ID

    try:
        # 创建JWT的载荷 (Payload)
        # 不设置 'exp' (expiration time) 字段，这样生成的token就不会过期。
        payload = {
            'user_id': USER_ID_FOR_SCRIPT,
            'iat': datetime.datetime.now(datetime.timezone.utc) # iat (Issued At) 记录token签发时间
        }

        # 使用 HS256 算法对载荷进行签名，生成最终的token
        permanent_token = jwt.encode(
            payload,
            SECRET_KEY,
            algorithm='HS256'
        )

        print("✅ 永久 Token 生成成功！")
        print("-" * 50)
        print("请将下面这一长串字符完整复制到 config.py 的 AUTH_TOKEN 字段中：")
        print(f"\n{permanent_token}\n")
        print("-" * 50)

    except ImportError:
        print("错误：缺少 PyJWT 库。请先运行 'pip install PyJWT'。")
    except Exception as e:
        print(f"生成Token时发生错误: {e}")

if __name__ == '__main__':
    generate_permanent_token()
