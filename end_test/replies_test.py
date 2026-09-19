"""评论回复：POST /api/data/replies  {aweme_id, comment_id, cursor, count}

注意：reply 端点要用「真 bdms」的 a_bogus，后端走 signing/comment_reply（默认 nv8）。
建议先把常驻 nv8 服务起了：signing/_shared/start_nv8_service.bat（否则每次多 ~5s）。
"""
from _common import post

post('/api/data/replies', {
    'aweme_id': '7626316866109066511',
    'comment_id': '7626681743785050939',
    'cursor': 0,
    'count': 20,
})
