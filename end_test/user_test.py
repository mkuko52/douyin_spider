"""用户信息：POST /api/data/user  {sec_user_id}

sec_user_id 从视频/评论响应的 author.sec_uid 取（或分享主页链接里的 sec_uid）。
"""
from _common import post

post('/api/data/user', {
    'sec_user_id': 'MS4wLjABAAAApBXenoFyCKJlEi9DItxR21JPOlhmiGbMiRGugv4aPbZxc6615SAQ7kctt1Lhq_Qa',
})
