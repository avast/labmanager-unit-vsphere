from web.modeltr.connection import Connection


async def disuse_db_conn_response(request, response):
    try:
        Connection.disuse()
    except:
        pass

