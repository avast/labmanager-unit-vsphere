import psycopg2
import json
from .base import trId, trLock
from .base import __all__ as MODELTR_TYPES_LIST
from .enums import StrEnumBase
import datetime
import inspect
import logging
from web.settings import Settings

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


class Document:
    id = trId
    __datetime_format = "%Y-%m-%d %H:%M:%S"

    def __init__(self, **kwargs):
        types = {}
        model_types = {}
        document_updated_property = None
        self.__logger = logging.getLogger(__name__)

        if '_defaults' not in type(self).__dict__:
            self._defaults = {}

        for item in inspect.getmembers(type(self)):
            member_name = item[0]
            member_value = item[1]
            if inspect.isclass(member_value) and member_value.__name__ in MODELTR_TYPES_LIST:
                # store types of each document entry
                types.update({member_name: member_value._type})
                model_types.update({member_name: member_value})

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
        self.__model_types = model_types
        self.__document_updated_property = document_updated_property
        # check for wrong arguments
        for arg in kwargs:
            if arg not in self.__types:
                raise RuntimeError(f'Unexpected property: {arg} used')

        # setup collection name
        self.collection_name = type(self).__name__.lower()

    def __check_types(self):
        for prop, typ in self.__types.items():
            prop_type = type(getattr(self, prop))
            if prop_type != typ:
                raise ValueError(f'property {prop} has unexpected type: {prop_type} instead of {typ}')

    def save(self, **kwargs):
        self.__check_types()
        if 'conn' not in kwargs:
            raise ValueError('conn not specified while saving some Document')

        if self.__document_updated_property:
            # self.__logger.debug(f'setting document updated at property for {type(self).__name__.lower()} {self.id}')
            setattr(self, self.__document_updated_property, datetime.datetime.now())

        if self.id == trId._default:
            self.__insert(**kwargs)
        else:
            self.__save(**kwargs)

    @staticmethod
    def __get_connection(**kwargs):
        if type(kwargs['conn']).__name__ == 'Connection':
            return kwargs['conn']

        if type(kwargs['conn']).__name__ == 'Transaction':
            return kwargs['conn'].conn

        raise RuntimeError()

    def __save(self, **kwargs):
        # self.__logger.debug(f'saving {type(self).__name__.lower()} {self.id}')
        connection = self.__get_connection(**kwargs)

        cur = connection.get_cursor()
        # self.__logger.debug(self.to_dict(redacted=True, show_hidden=True))
        cur.execute(
            "update documents set data= %s where id = %s",
            [json.dumps(self.to_dict(show_hidden=True)), self.id]
        )
        connection.wait_for_completion()

    def __insert(self, **kwargs):
        connection = self.__get_connection(**kwargs)

        cur = connection.get_cursor()
        self.__logger.debug(self.to_dict(show_hidden=True))
        cur.execute(
            "insert into documents (type, data) VALUES(%s,%s) returning id;",
            [type(self).__name__.lower(), json.dumps(self.to_dict(show_hidden=True))]
        )
        connection.wait_for_completion()
        returning_id = cur.fetchone()[0]
        self.id = str(returning_id)

    def to_dict(self, redacted=None, show_hidden=False):
        result = {}
        for prop, typ in self.__types.items():
            output_value = getattr(self, prop)
            current_model_type = self.__model_types[prop].__name__

            # do not include ID to dict
            if prop == 'id':
                continue
            # do not show hidden strings if wanted
            elif not show_hidden and current_model_type == "trHiddenString":
                continue
            # stringify timestamp
            elif isinstance(output_value, datetime.datetime):
                output_value = output_value.strftime(self.__datetime_format)
            # stringify enum
            elif issubclass(typ, StrEnumBase):
                output_value = output_value.value
            else:
                MAXIMUM_VALUE_LENGTH = 100  # Limit in order to prevent excessively long data, such as base 64
                value_length = len(str(output_value))
                if redacted and value_length > MAXIMUM_VALUE_LENGTH:
                    val_redacted = str(output_value)[:MAXIMUM_VALUE_LENGTH]
                    output_value = f'{val_redacted}... redacted'

            result[prop] = output_value

        return result

    @classmethod
    def _db_record_to_instance_pq(cls, record):
        record_id = record[0]
        record_data = record[2]
        new_document = cls(id=str(record_id))
        for prop, val in record_data.items():
            # every field that is stored in the db and is not defined in model will be inaccessible
            if prop not in new_document.__types:
                continue

            target_type = new_document.__types[prop]

            # convert str to datetime.datetime instance
            if target_type == datetime.datetime:
                try:
                    cv = datetime.datetime.strptime(val, cls.__datetime_format)
                except ValueError:
                    cv = datetime.datetime.min
                setattr(
                    new_document,
                    prop,
                    cv
                )
            # convert strEnums back to instances
            elif issubclass(target_type, StrEnumBase):
                enum_type = new_document.__types[prop]
                setattr(new_document, prop, enum_type(val))
            else:
                setattr(new_document, prop, val)
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
        if 'conn' not in kwargs:
            raise ValueError('parameter conn must be specified')
        connection = kwargs['conn']

        result = DocumentList()
        sql_query = cls.construct_query(query)

        cur = connection.get_cursor()
        cur.execute(sql_query[0], sql_query[1])
        connection.wait_for_completion()
        if cur.rowcount == 0 and Settings.app['document_abstraction']['warn_0_records']:
            logger = logging.getLogger(__name__)
            logger.debug(f'0 records returned from: >>{cur.query}<<')
        for item in cur.fetchall():
            result.append(cls._db_record_to_instance_pq(item))
        return result

    @classmethod
    def __get_one_custom(cls, query, extend, **kwargs):
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
            logger = logging.getLogger(__name__)
            logger.error('OperationalError while processing request: ', exc_info=True)
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
            logger = logging.getLogger(__name__)
            logger.error('OperationalError while processing request: ', exc_info=True)
            return None

    @classmethod
    def get_lock_field(cls):
        for item in inspect.getmembers(cls):
            if inspect.isclass(item[1]) and item[1] is trLock:
                return item[0]
        raise ValueError('lock field cannot be found')

    @classmethod
    def get_eldest_excl(cls, query, **kwargs):
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

    @classmethod
    def delete(cls, query, **kwargs):
        if 'conn' not in kwargs:
            raise ValueError('parameter conn must be specified')
        connection = kwargs['conn']

        if not isinstance(query, type({})):
            raise ValueError('query must be a dictionary')

        if "_id" not in query:
            raise ValueError('there must be _id in query')

        cur = connection.get_cursor()
        cur.execute("DELETE FROM documents where type=%s and id=%s", [cls.__name__.lower(), str(query["_id"])])

        connection.wait_for_completion()
