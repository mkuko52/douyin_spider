"""评论列表：POST /api/data/comments  {aweme_id, cursor, count}"""
from _common import post

post('/api/data/comments', {
    'aweme_id': '7626316866109066511',
    'cursor': 0,
    'count': 20,
})
