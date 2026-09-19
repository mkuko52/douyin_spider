"""视频列表（推荐）：POST /api/data/feed  {count, refresh_index}"""
from _common import post

post('/api/data/feed', {
    'count': 10,
    'refresh_index': 1,
})
