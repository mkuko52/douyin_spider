"""登录：POST /api/auth/sms_login  {phone, code}

登录成功返回的 token 会被 `_common.post` 自动写进 token.txt，供其他 *_test.py 用。
"""
from _common import post

post('/api/auth/sms_login', {
    'phone': '13800138000',   # 占位号，运行前改成自己的测试号码
    'code': '123456',
})
