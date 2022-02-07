import logging

logger = logging.getLogger()


async def auth(request):
    if 'LDAP_AUTHORISED_LOGIN' in request.headers:
        request.headers['AUTHORISED_LOGIN'] = request.headers['LDAP_AUTHORISED_LOGIN']
        logger.debug('authorised login set from auth_ldap module')
