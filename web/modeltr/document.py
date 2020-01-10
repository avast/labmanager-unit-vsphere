import psycopg2
import json
from .base import trString, trList, trId, trSaveTimestamp, trLock
from .base import __all__ as MODELTR_TYPES_LIST
import datetime
import inspect
import logging


class DocumentList(list):

    def __init__(self):
        self.__logger = logging.getLogger(__name__)
        super().__init__(self)

    def first(self):
        if len(self):
            return self[0]
        else:
            self.__logger.debug('Empty documentlist')
            raise RuntimeError('query yielded no result')


class Document(object):
    id = trId
    __datetime_format = "%Y-%m-%d %H:%M:%S"

    def __init__(self, **kwargs):
        types = {}
        document_updated_property = None
        if '_defaults' not in type(self).__dict__:
            self._defaults = {}

        for item in inspect.getmembers(type(self)):
            member_name = item[0]
            member_value = item[1]
            if inspect.isclass(member_value) and member_value.__name__ in MODELTR_TYPES_LIST:
                # store types of each document entry
                types.update({member_name: member_value._type})

                if member_value.__name__ == 'trSaveTimestamp':
                    document_updated_property = member_name

                # set up default values where available
                if member_name in self._defaults:
                    setattr(self, member_name, self._defaults[member_name])
                else:
                    setattr(self, member_name, member_value._default)

                # set up values defined in constructor
                if member_name in kwargs:
                    setattr(self, member_name, kwargs[member_name])

        self.__types = types
        self.__document_updated_property = document_updated_property

        # check for wrong arguments
        for arg in kwargs:
            if arg not in self.__types:
                raise RuntimeError('Unexpected property: {} used'.format(arg))

        # setup collection name
        self.collection_name = type(self).__name__.lower()

        self.__logger = logging.getLogger(__name__)

    def __check_types(self):
        for prop, typ in self.__types.items():
            if type(getattr(self, prop)) != typ:
                raise ValueError(
                    'property {} has unexpected type: {} instead of {}'.format(
                        prop,
                        type(getattr(self, prop)),
                        typ
                    )
                )

    def save(self, **kwargs):
        self.__check_types()
        if 'conn' not in kwargs:
            raise ValueError('conn not specified while saving some Document')

        if self.__document_updated_property:
            self.__logger.debug('setting document updated at property for {} {}'.format(
                type(self).__name__.lower(),
                self.id
            ))
            setattr(self, self.__document_updated_property, datetime.datetime.now())

        if self.id == trId._default:
            self.__insert(**kwargs)
        else:
            self.__save(**kwargs)

    def __get_connection(self, **kwargs):
        if type(kwargs['conn']).__name__ == 'Connection':
            return kwargs['conn']

        if type(kwargs['conn']).__name__ == 'Transaction':
            return kwargs['conn'].conn

        raise RuntimeError()

    def __save(self, **kwargs):
        self.__logger.debug('saving {} {}'.format(type(self).__name__.lower(), self.id))
        connection = self.__get_connection(**kwargs)

        cur = connection.get_cursor()
        self.__logger.debug(self.to_dict())
        cur.execute(
                    "update documents set data= %s where id = %s",
                    [json.dumps(self.to_dict()), self.id]
        )
        connection.wait_for_completion()

    def __insert(self, **kwargs):
        connection = self.__get_connection(**kwargs)

        cur = connection.get_cursor()
        self.__logger.debug(self.to_dict())
        cur.execute(
                    "insert into documents (type, data) VALUES(%s,%s) returning id;",
                    [type(self).__name__.lower(), json.dumps(self.to_dict())]
        )
        connection.wait_for_completion()
        returning_id = cur.fetchone()[0]
        self.id = str(returning_id)

    def to_dict(self):
        result = {}
        for prop, typ in self.__types.items():
            if prop == 'id':
                continue
            if isinstance(getattr(self, prop), type(datetime.datetime.now())):
                result.update({prop: getattr(self, prop).strftime(self.__datetime_format)})
            else:
                result.update({prop: getattr(self, prop)})
        return result

#    @classmethod
#    def __fix_query(cls, query):
#        new_query = {}
#        for key, val in query.items():
#            new_query[key] = val if key != '_id' else bson.objectid.ObjectId(val)
#        return new_query

#    @classmethod
#    def _db_record_to_instance(cls, record):
#        new_document = cls(id=str(record['_id']))
#        for prop in record.keys():
#            if prop != '_id':
#                setattr(new_document, prop, record[prop])
#        return new_document

    @classmethod
    def _db_record_to_instance_pq(cls, record):
        # print(record)
        record_id = record[0]
        record_data = record[2]
        new_document = cls(id=str(record_id))
        for prop in record_data.keys():
            # every field that is stored in the db and is not defined in model
            # will be inaccessible
            if prop not in new_document.__types:
                continue
            if isinstance(datetime.datetime.now(), new_document.__types[prop]):
                setattr(
                        new_document,
                        prop,
                        datetime.datetime.strptime(record_data[prop], cls.__datetime_format)
                )
            else:
                setattr(new_document, prop, record_data[prop])
        return new_document

    @classmethod
    def construct_query(cls, query):
        collection_name = cls.__name__.lower()
        sql_query = "SELECT * FROM documents where "
        params = []
        for key, val in query.items():
            if key == "_id":
                sql_query += " id = %s and "
                params += [str(val)]
            else:
                sql_query += " data::json->>%s = %s and "
                params += [key, str(val)]

        sql_query += " type = %s "
        params += [collection_name]
        return [sql_query, params]

    @classmethod
    def get(cls, query, **kwargs):
        collection_name = cls.__name__.lower()
        if 'conn' not in kwargs:
            raise ValueError('parameter conn must be specified')
        connection = kwargs['conn']

        result = DocumentList()
        sql_query = cls.construct_query(query)

        cur = connection.get_cursor()
        cur.execute(sql_query[0], sql_query[1])
        connection.wait_for_completion()
        # cur.execute("SELECT * FROM documents where id = %s;",[query["_id"]])
        if cur.rowcount == 0:
            print(cur.rowcount)
            print(cur.query)
        for item in cur.fetchall():
            result.append(cls._db_record_to_instance_pq(item))
        return result

        # collection = connection.client[connection.database][collection_name]
        # cresult = collection.find(cls.__fix_query(query), session=connection.session)
        # result = DocumentList()
        # for item in cresult:
        #     result.append(cls._db_record_to_instance(item))
        # return result

    @classmethod
    def __get_one_custom(cls, query, extend, **kwargs):
        collection_name = cls.__name__.lower()
        if 'conn' not in kwargs:
            raise ValueError('parameter conn must be specified')
        connection = kwargs['conn']

        sql_query = cls.construct_query(query)

        cur = connection.get_cursor()
        cur.execute(sql_query[0] + " " + extend, sql_query[1])
        connection.wait_for_completion()
        if cur.rowcount == 0:
            return None
        else:
            return cls._db_record_to_instance_pq(cur.fetchone())

    @classmethod
    def get_one(cls, query, **kwargs):
        return cls.__get_one_custom(query, "LIMIT 1;", **kwargs)

    @classmethod
    def get_one_for_update(cls, query, **kwargs):
        return cls.__get_one_custom(query, "LIMIT 1 FOR UPDATE;", **kwargs)

    @classmethod
    def get_one_for_update_nowait(cls, query, **kwargs):
        try:
            return cls.__get_one_custom(query, "LIMIT 1 FOR UPDATE NOWAIT;", **kwargs)
        except psycopg2.OperationalError as e:
            self.__logger.error('OperationalError while processing request: ', exc_info=True)
            return None

    @classmethod
    def get_one_for_update_skip_locked(cls, query, **kwargs):
        try:
            return cls.__get_one_custom(
                            query,
                            "ORDER BY ID LIMIT 1 FOR UPDATE SKIP LOCKED;",
                            **kwargs
            )
        except psycopg2.OperationalError as e:
            self.__logger.error('OperationalError while processing request: ', exc_info=True)
            return None

    @classmethod
    def get_lock_field(cls):
        for item in inspect.getmembers(cls):
            if inspect.isclass(item[1]) and item[1] is trLock:
                return item[0]
        raise ValueError('lock field cannot be found')

    @classmethod
    def get_eldest_excl(cls, query,  **kwargs):
        collection_name = cls.__name__.lower()
        if 'conn' not in kwargs:
            raise ValueError('parameter conn must be specified')
        connection = kwargs['conn']

        if not isinstance(query, type({})):
            raise ValueError('query must be a dictionary')

        # get the lock field, only one such field can be present in the model
        lock_field = cls.get_lock_field()

        cur = connection.get_cursor()

        sql_query = cls.construct_query(query)
        cur.execute(sql_query[0] + " ORDER BY ID LIMIT 1 FOR UPDATE SKIP LOCKED;", sql_query[1])
        connection.wait_for_completion()

        result = cur.fetchone()
        if result is None:
            return None

        # update lock field
        doc = cls._db_record_to_instance_pq(result)
        setattr(doc, lock_field, getattr(doc, lock_field) + 1)
        doc.save(conn=connection)

        return doc
