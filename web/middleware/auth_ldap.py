from web.settings import Settings as settings
import asyncio
import logging
import sys
import datetime
import time
import base64
import hashlib
from sanic.response import json as sanicjson
import ldap

logger = logging.getLogger()


def get_ldap_connection(username, password):
    if not settings.app['service']['ldap'].get('cert_check', True):
        ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
    l_obj = ldap.initialize(settings.app['service']['ldap']['url'])
    l_obj.set_option(ldap.OPT_TIMEOUT, 8)
    l_obj.protocol_version = ldap.VERSION3
    try:
        l_obj.simple_bind_s(username, password)
        return l_obj
    except Exception as ex:
        logger.warning("Svc-like auth attempt failed, trying user-like attempt...")
        try:
            l_obj.simple_bind_s(
                "{}@{}".format(username, settings.app['service']['ldap']['domain_name']),
                password
            )
            return l_obj
        except Exception as iex:
            logger.error(
                "An exception occured when connecting to ldap: {}".format(iex)
            )
        return None
    return None


def terminate_ldap_connection(conn):
    conn.unbind_s()


async def parse_auth(request):
    auth_string = request.headers['authorization']
    if auth_string.find("Basic ") == 0:
        hash_string = auth_string[6:]
        base64_bytes = hash_string.encode('ascii')
        message_bytes = base64.b64decode(base64_bytes)
        message = message_bytes.decode('ascii')
        mess_arr = message.split(':', 1)
        return {'username': mess_arr[0], 'password': mess_arr[1]}
    else:
        return None


async def anonymize_password(password):
    md5_passwd = hashlib.md5(password.encode('ascii')).hexdigest()
    return md5_passwd


def get_user_dn(conn, username):
    try:
        res = conn.search_s(
            settings.app['service']['ldap']['base_dn'],
            ldap.SCOPE_SUBTREE,
            attrlist=[],
            filterstr="(&(objectClass=user)(sAMAccountName={}))".format(username)
        )
        auth_user_dn = res[0][0]
        return auth_user_dn
    except Exception as ex:
        return None


def check_group(conn, group_dn, user_dn):
    try:
        result = conn.search_s(
            group_dn,
            ldap.SCOPE_BASE,
            filterstr="(&(objectClass=group)(member={}))".format(user_dn),
            attrlist=["name"],
        )
        is_a_member = result[0][0] == group_dn
        return is_a_member
    except Exception as ex:
        logger.warning("Failed check in group: {}".format(group_dn))
        return False


async def auth(request):
    if 'authorization' not in request.headers:
        return sanicjson(
            {"error": "you cannot be authenticated to access the service, no credentials provided"},
            401
        )

    loop = asyncio.get_event_loop()
    auth_struct = await parse_auth(request)
    anonymized_passwd = await anonymize_password(auth_struct['password'])

    logger.debug("An attempt to auth: {}:{}".format(auth_struct['username'], anonymized_passwd))
    conn = await loop.run_in_executor(None, get_ldap_connection, auth_struct['username'], auth_struct['password'])
    if conn is None:
        logger.warning("wrong credentials for: {}".format(auth_struct['username']))
        return sanicjson({"error": "you cannot be authenticated to access the service"}, 401)
    try:
        user_dn = await loop.run_in_executor(None, get_user_dn, conn, auth_struct['username'])
        user_group_dn = settings.app['service']['ldap']['ugroup']

        is_auth_as_user = await loop.run_in_executor(None, check_group, conn, user_group_dn, user_dn)
        if is_auth_as_user:
            request.headers['LDAP_AUTHORISED_LOGIN'] = auth_struct['username']
            request.headers['LDAP_AUTHORISED_DN'] = user_dn
            request.headers['AUTHORISED_AS'] = 'user'
            return

        admin_group_dn = settings.app['service']['ldap']['agroup']
        is_auth_as_admin = await loop.run_in_executor(None, check_group, conn, admin_group_dn, user_dn)
        if is_auth_as_admin:
            request.headers['LDAP_AUTHORISED_LOGIN'] = auth_struct['username']
            request.headers['LDAP_AUTHORISED_DN'] = user_dn
            request.headers['AUTHORISED_AS'] = 'admin'
            return

        return sanicjson({"error": "you are not authorized to see the content"}, 403)
    finally:
        await loop.run_in_executor(None, terminate_ldap_connection, conn)
