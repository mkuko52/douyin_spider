"""发码：POST /api/auth/send_code  {phone}   （会给该号码发真短信）"""
from _common import post

post('/api/auth/send_code', {
    'phone': '13800138000',   # 占位号，运行前改成自己的测试号码
})
