from mamba import description, context, it
from expects import *
from unittest.mock import Mock

from web.modeltr.document import Document as Document
from web.modeltr.document import DocumentList as DocumentList
import web.modeltr.base as tr_types
import sys
import bson

TESTED_CLASS = 'Document'


with description('Document'):
    with before.each:
        self.mongomock = Mock()
        self.mongomock.find_one_and_update = Mock(return_value=None)
        self.mongomock.insert_one = Mock(return_value=Mock(
            inserted_id='foo',
        ))
        self.mongomock.update_one = Mock(return_value=Mock(
            raw_result='foo',
            modified_count=10,
            matched_count=10
        ))
        self.mongomock.find = Mock(return_value=[
            {'_id': 'foo'},
            {'_id': 'bar'},
            {'_id': 'def'}
        ])
        self.conn = Mock()
        self.conn.database = 'fake_database'
        self.conn.client = {
                self.conn.database: {
                    TESTED_CLASS.lower(): self.mongomock
                }
            }

    with context('class->get_eldest_excl()'):
        with before.each:
            # replaces methods that are called and aren't tested
            # method called directly
            # Document._Document__fix_query = (lambda arg: arg) # this is private class method
            # Document.get_lock_field = (lambda: 'foo')         # this is public class method
            # methods called via mock (statistics about usage are stored)
            self.o_fq = Document.__dict__['_Document__fix_query']
            Document._Document__fix_query = Mock(side_effect=(lambda arg: arg))
            self.o_glf = Document.__dict__['get_lock_field']
            Document.get_lock_field = Mock(return_value='foo')

        with after.each:
            # return mocked values back
            Document._Document__fix_query = self.o_fq
            Document.get_lock_field = self.o_glf

        with it('raises an exception when nothing is passed as an argument'):
            expect(lambda: Document.get_eldest_excl()).to(raise_error)

        with it('raises an exception when query is not a dictionary'):
            expect(lambda: Document.get_eldest_excl()).to(raise_error)

        with it('raises an exception when conn parameter is not specified'):
            expect(lambda: Document.get_eldest_excl('foo')).to(raise_error(ValueError))

        with it('returns None when nothing is found in the underlying database'):

            Document.get_eldest_excl({}, conn=self.conn)

            self.mongomock.find_one_and_update.assert_called_once
            Document.get_lock_field.assert_called_once()
            Document._Document__fix_query.assert_called_once()

        with it('returns None when weird data are returned from underlying database'):

            self.mongomock.find_one_and_update = Mock(
                return_value={'corrupted foo': 'bar response'}
            )

            Document.get_eldest_excl({}, conn=self.conn)
            self.mongomock.find_one_and_update.assert_called_once()
            Document.get_lock_field.assert_called_once()
            Document._Document__fix_query.assert_called_once()

        with it(
            'returns an instance with correct id when correct data are returned from underlying db'
        ):

            fake_id = 'quuux'
            self.mongomock.find_one_and_update = Mock(return_value={'_id': fake_id})

            doc = Document.get_eldest_excl({}, conn=self.conn)

            self.mongomock.find_one_and_update.assert_called_once()
            Document.get_lock_field.assert_called_once()
            Document._Document__fix_query.assert_called_once()
            expect(doc.id).to(be(fake_id))

    with context('class->get_lock_field()'):

        with it('returns lock field when one specified'):

            class Bfoo(Document):
                foobar = tr_types.trLock

            expect(Bfoo.get_lock_field()).to(equal('foobar'))

        with it('returns lock field when two specified'):

            class Bbar(Document):
                foobar = tr_types.trLock
                bazquux = tr_types.trLock
            expect(Bbar.get_lock_field()).to(equal('bazquux'))

        with it('raises exception when no lock specified'):
            expect(lambda: Document.get_eldest_excl('foo')).to(raise_error(ValueError))

    with context('class->get()'):

        with it('raises an exception when no connection is provided'):
            expect(lambda: Document.get({})).to(raise_error(ValueError))

        with it('returns DocumentList object'):
            expect(Document.get({}, conn=self.conn)).to(be_an(DocumentList))

        with it('returns expected data'):

            returned = Document.get({}, conn=self.conn)

            expect(len(returned)).to(equal(3))
            expect(returned[0].id).to(equal('foo'))
            expect(returned[1].id).to(equal('bar'))
            expect(returned[2].id).to(equal('def'))

        with it('uses given connection'):

            Document.get({}, conn=self.conn)
            self.mongomock.find.assert_called_once()

    with context('class->_db_record_to_instance()'):

        with it('converts db object to correct instance'):

            doc = Document._db_record_to_instance(self.mongomock.find()[1])
            expect(doc.id).to(equal('bar'))
            expect(doc).to(be_a(Document))

        with it('converts custom db object to correct instance'):

            self.mongomock.find = Mock(return_value=[
                {'_id': 'foo'},
                {'_id': 'bar', 'foo': 'garply'},
                {'_id': 'def'}
            ])

            class Quux(Document):
                foo = tr_types.trString

            doc = Quux._db_record_to_instance(self.mongomock.find()[1])
            expect(doc.id).to(equal('bar'))
            expect(doc.foo).to(equal('garply'))
            expect(doc).to(be_a(Document))

    with context('class->__fix_query()'):

        with it('converts _id field to bson type to be properly used by underlying library'):

            fixed = Document._Document__fix_query({
                '_id': '5ba1fc0304c3a95915381fd5',
                'foo': 'bar',
                'baz': 'qux',
                'def': 'garply'
            })

            expect(fixed['_id']).to(be_a(bson.objectid.ObjectId))
            expect(fixed['foo']).to(equal('bar'))
            expect(fixed['baz']).to(equal('qux'))
            expect(fixed['def']).to(equal('garply'))

    with context('to_dict()'):

        with it('converts object to dictionary, id is omitted'):

            class Quux(Document):
                foo = tr_types.trString
                bar = tr_types.trInt
                baz = tr_types.trString
                _defaults = {
                    'foo': 'def',
                    'bar': 34567753,
                    'baz': 'henk'
                }

            dict = Quux().to_dict()
            expect(dict).to(have_keys('foo', 'bar', 'baz'))
            expect(dict).not_to(have_key('id'))
            expect(dict['foo']).to(equal('def'))
            expect(dict['bar']).to(equal(34567753))
            expect(dict['baz']).to(equal('henk'))

    with context('save()'):

        with it('raises an exception when no connection specified'):
            expect(lambda: Document().save()).to(raise_error(ValueError))

        with it('calls __save() when documment should be saved'):
            doc = Document()
            doc.id = '+1'
            doc._Document__insert = Mock()
            doc._Document__save = Mock()
            doc.save(conn=self.conn)
            doc._Document__save.assert_called_once()
            doc._Document__insert.assert_not_called()

        with it('calls __insert() when documment should be inserted'):
            doc = Document()
            doc._Document__insert = Mock()
            doc._Document__save = Mock()
            doc.save(conn=self.conn)
            doc._Document__save.assert_not_called()
            doc._Document__insert.assert_called_once()

    with context('__save()'):

        with it('gets connection'):

            doc = Document()
            doc.id = '5ba1fc1304c3a95915381fd5'
            doc._Document__get_connection = Mock(return_value=self.conn)
            doc._Document__save()
            doc._Document__get_connection.assert_called_once()

        with it('calls underlying database library to save the data'):

            doc = Document()
            doc.id = '5ba1fc1304c3a95915381fd5'
            doc._Document__get_connection = Mock(return_value=self.conn)
            doc._Document__save()
            self.mongomock.update_one.assert_called_once()

    with context('__insert()'):

        with it('gets connection'):

            doc = Document()
            doc._Document__get_connection = Mock(return_value=self.conn)
            doc._Document__insert()
            doc._Document__get_connection.assert_called_once()

        with it('calls underlying database library to insert the data'):

            doc = Document()
            doc._Document__get_connection = Mock(return_value=self.conn)
            doc._Document__insert()
            self.mongomock.insert_one.assert_called_once()

        with it('sets corectly up the returning id'):

            doc = Document()
            doc._Document__get_connection = Mock(return_value=self.conn)
            doc._Document__insert()
            expect(doc.id).to(equal('foo'))

    with context('__get_connection()'):

        with it('returns connection when Connection passed in'):

            class Connection():
                pass

            doc = Document()
            conn = Connection()
            expect(doc._Document__get_connection(conn=conn)).to(equal(conn))

        with it('returns bound connection of transaction when Transaction passed in'):

            class Transaction():
                pass

            class Connection():
                pass

            doc = Document()
            conn = Connection()
            tr = Transaction()
            tr.conn = conn
            expect(doc._Document__get_connection(conn=tr)).to(equal(conn))

        with it('raises an exception when something else is passed in'):

            class Garply():
                pass

            doc = Document()
            conn = Garply()

            expect(lambda: doc._Document__get_connection(conn=conn)).to(
                raise_error(RuntimeError)
            )

    with context('__init__()'):

        with it('raises an exception when unexpected parameters is given'):

            expect(lambda: Document(foo='garply')).to(
                raise_error(RuntimeError)
            )

        with it('sets default id up'):

            doc = Document()
            expect(doc.id).to(equal('<null>'))

        with it('sets defaults defined in custom class up'):

            class Def(Document):
                foo = tr_types.trString
                bar = tr_types.trString
                _defaults = {'foo': 'quux', 'bar': 'qux'}

            doc = Def()
            expect(doc.id).to(equal('<null>'))
            expect(doc.foo).to(equal('quux'))
            expect(doc.bar).to(equal('qux'))

        with it('sets defaults defined in constructor  up'):

            class Def(Document):
                foo = tr_types.trString
                bar = tr_types.trString

            doc = Def(foo='quux', bar='qux')
            expect(doc.id).to(equal('<null>'))
            expect(doc.foo).to(equal('quux'))
            expect(doc.bar).to(equal('qux'))

        with it('prefers values from constructor'):

            class Def(Document):
                foo = tr_types.trString
                bar = tr_types.trString
                _defaults = {'foo': 'quux', 'bar': 'qux'}

            doc = Def(foo='wobble', bar='henk')
            expect(doc.id).to(equal('<null>'))
            expect(doc.foo).to(equal('wobble'))
            expect(doc.bar).to(equal('henk'))

        with it('sets coorectly up the inner field collection_name'):

            class Def(Document):
                foo = tr_types.trString
                bar = tr_types.trString
                _defaults = {'foo': 'quux', 'bar': 'qux'}

            doc = Def(foo='wobble', bar='henk')
            expect(doc.collection_name).to(equal('def'))

with description('Document List'):

    with context('first()'):

        with it('raises an exception when list is empty'):
            expect(lambda: DocumentList().first()).to(raise_error(RuntimeError))

        with it('returns first element when there is one element in the list'):
            list = DocumentList()
            list.append('foo')
            expect(list.first()).to(equal('foo'))

        with it('returns first element when there is more elements in the list'):
            list = DocumentList()
            list.append('foo')
            list.append('bar')
            list.append('baz')
            list.append('qux')
            expect(list.first()).to(equal('foo'))
