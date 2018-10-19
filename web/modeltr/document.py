import pymongo
import bson
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

    def __init__(self, **kwargs):
        types = {}
        if '_defaults' not in type(self).__dict__:
            self._defaults = {}

        for item in inspect.getmembers(type(self)):
            if inspect.isclass(item[1]) and item[1].__name__ in MODELTR_TYPES_LIST:
                # store types of each document entry
                types.update({item[0]: item[1]._type})

                # set up default values where available
                if item[0] in self._defaults:
                    setattr(self, item[0], self._defaults[item[0]])
                else:
                    setattr(self, item[0], item[1]._default)

                # set up values defined in constructor
                if item[0] in kwargs:
                    setattr(self, item[0], kwargs[item[0]])

        self.__types = types

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
        self.__logger.debug('saving document {}'.format(self.id))
        # TODO: updated_at must be handled here
        connection = self.__get_connection(**kwargs)
        result = connection.client[connection.database][self.collection_name].update_one(
            filter={'_id': bson.objectid.ObjectId(self.id)},
            update={'$set': self.to_dict()}, session=connection.session
        )

        self.__logger.debug(
            'document saved {}\n  raw_result: {}\n  modified_count: {}\n  matched_count: {}'.format(
                self.id,
                result.raw_result,
                result.modified_count,
                result.matched_count
            )
        )

    def __insert(self, **kwargs):
        connection = self.__get_connection(**kwargs)
        collection = connection.client[connection.database][self.collection_name]
        result = collection.insert_one(self.to_dict(), session=connection.session)
        self.id = str(result.inserted_id)

    def to_dict(self):
        result = {}
        for prop, typ in self.__types.items():
            if prop != 'id':
                result.update({prop: getattr(self, prop)})
        return result

    @classmethod
    def __fix_query(cls, query):
        new_query = {}
        for key, val in query.items():
            new_query[key] = val if key != '_id' else bson.objectid.ObjectId(val)
        return new_query

    @classmethod
    def _db_record_to_instance(cls, record):
        new_document = cls(id=str(record['_id']))
        for prop in record.keys():
            if prop != '_id':
                setattr(new_document, prop, record[prop])
        return new_document

    @classmethod
    def get(cls, query, **kwargs):
        collection_name = cls.__name__.lower()
        if 'conn' not in kwargs:
            raise ValueError('parameter conn must be specified')
        connection = kwargs['conn']

        collection = connection.client[connection.database][collection_name]
        cresult = collection.find(cls.__fix_query(query), session=connection.session)
        result = DocumentList()
        for item in cresult:
            result.append(cls._db_record_to_instance(item))
        return result

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
        cresult = connection.client[connection.database][collection_name].find_one_and_update(
            cls.__fix_query(query),
            {'$inc': {cls.get_lock_field(): 1}},
            sort=[('_id', -1)],
            upsert=False,
            session=connection.session
        )
        if cresult is None or '_id' not in cresult:
            return None

        return cls._db_record_to_instance(cresult)
