"""关键词搜索：POST /api/data/search  {keyword, offset, count}

需要「真 www 登录态」，否则会返回 2483 请先登录。
"""
from _common import post

post('/api/data/search', {
    'keyword': 'minecraft',
    'offset': 0,
    'count': 20,
})
