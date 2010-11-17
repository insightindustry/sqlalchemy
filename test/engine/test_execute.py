from sqlalchemy.test.testing import eq_, assert_raises
import re
from sqlalchemy.interfaces import ConnectionProxy
from sqlalchemy import MetaData, Integer, String, INT, VARCHAR, func, \
    bindparam, select
from sqlalchemy.test.schema import Table, Column
import sqlalchemy as tsa
from sqlalchemy.test import TestBase, testing, engines
import logging
from sqlalchemy.dialects.oracle.zxjdbc import ReturningParam

users, metadata = None, None
class ExecuteTest(TestBase):
    @classmethod
    def setup_class(cls):
        global users, users_autoinc, metadata
        metadata = MetaData(testing.db)
        users = Table('users', metadata,
            Column('user_id', INT, primary_key = True, autoincrement=False),
            Column('user_name', VARCHAR(20)),
        )
        users_autoinc = Table('users_autoinc', metadata,
            Column('user_id', INT, primary_key = True,
                                    test_needs_autoincrement=True),
            Column('user_name', VARCHAR(20)),
        )
        metadata.create_all()

    @engines.close_first
    def teardown(self):
        testing.db.connect().execute(users.delete())
        
    @classmethod
    def teardown_class(cls):
        metadata.drop_all()

    @testing.fails_on_everything_except('firebird', 'maxdb',
                                        'sqlite', '+pyodbc',
                                        '+mxodbc', '+zxjdbc', 'mysql+oursql',
                                        'informix+informixdb')
    def test_raw_qmark(self):
        for conn in testing.db, testing.db.connect():
            conn.execute('insert into users (user_id, user_name) '
                         'values (?, ?)', (1, 'jack'))
            conn.execute('insert into users (user_id, user_name) '
                         'values (?, ?)', [2, 'fred'])
            conn.execute('insert into users (user_id, user_name) '
                         'values (?, ?)', [3, 'ed'], [4, 'horse'])
            conn.execute('insert into users (user_id, user_name) '
                         'values (?, ?)', (5, 'barney'), (6, 'donkey'))
            conn.execute('insert into users (user_id, user_name) '
                         'values (?, ?)', 7, 'sally')
            res = conn.execute('select * from users order by user_id')
            assert res.fetchall() == [
                (1, 'jack'),
                (2, 'fred'),
                (3, 'ed'),
                (4, 'horse'),
                (5, 'barney'),
                (6, 'donkey'),
                (7, 'sally'),
                ]
            conn.execute('delete from users')

    # some psycopg2 versions bomb this.
    @testing.fails_on_everything_except('mysql+mysqldb',
            'mysql+mysqlconnector', 'postgresql')
    @testing.fails_on('postgresql+zxjdbc', 'sprintf not supported')
    def test_raw_sprintf(self):
        for conn in testing.db, testing.db.connect():
            conn.execute('insert into users (user_id, user_name) '
                         'values (%s, %s)', [1, 'jack'])
            conn.execute('insert into users (user_id, user_name) '
                         'values (%s, %s)', [2, 'ed'], [3, 'horse'])
            conn.execute('insert into users (user_id, user_name) '
                         'values (%s, %s)', 4, 'sally')
            conn.execute('insert into users (user_id) values (%s)', 5)
            res = conn.execute('select * from users order by user_id')
            assert res.fetchall() == [(1, 'jack'), (2, 'ed'), (3,
                    'horse'), (4, 'sally'), (5, None)]
            conn.execute('delete from users')

    # pyformat is supported for mysql, but skipping because a few driver
    # versions have a bug that bombs out on this test. (1.2.2b3,
    # 1.2.2c1, 1.2.2)

    @testing.skip_if(lambda : testing.against('mysql+mysqldb'),
                     'db-api flaky')
    @testing.fails_on_everything_except('postgresql+psycopg2',
            'postgresql+pypostgresql', 'mysql+mysqlconnector')
    def test_raw_python(self):
        for conn in testing.db, testing.db.connect():
            conn.execute('insert into users (user_id, user_name) '
                         'values (%(id)s, %(name)s)', {'id': 1, 'name'
                         : 'jack'})
            conn.execute('insert into users (user_id, user_name) '
                         'values (%(id)s, %(name)s)', {'id': 2, 'name'
                         : 'ed'}, {'id': 3, 'name': 'horse'})
            conn.execute('insert into users (user_id, user_name) '
                         'values (%(id)s, %(name)s)', id=4, name='sally'
                         )
            res = conn.execute('select * from users order by user_id')
            assert res.fetchall() == [(1, 'jack'), (2, 'ed'), (3,
                    'horse'), (4, 'sally')]
            conn.execute('delete from users')

    @testing.fails_on_everything_except('sqlite', 'oracle+cx_oracle', 'informix+informixdb')
    def test_raw_named(self):
        for conn in testing.db, testing.db.connect():
            conn.execute('insert into users (user_id, user_name) '
                         'values (:id, :name)', {'id': 1, 'name': 'jack'
                         })
            conn.execute('insert into users (user_id, user_name) '
                         'values (:id, :name)', {'id': 2, 'name': 'ed'
                         }, {'id': 3, 'name': 'horse'})
            conn.execute('insert into users (user_id, user_name) '
                         'values (:id, :name)', id=4, name='sally')
            res = conn.execute('select * from users order by user_id')
            assert res.fetchall() == [(1, 'jack'), (2, 'ed'), (3,
                    'horse'), (4, 'sally')]
            conn.execute('delete from users')

    def test_exception_wrapping(self):
        for conn in testing.db, testing.db.connect():
            try:
                conn.execute('osdjafioajwoejoasfjdoifjowejfoawejqoijwef'
                             )
                assert False
            except tsa.exc.DBAPIError:
                assert True

    def test_empty_insert(self):
        """test that execute() interprets [] as a list with no params"""

        result = \
            testing.db.execute(users_autoinc.insert().
                        values(user_name=bindparam('name')), [])
        eq_(testing.db.execute(users_autoinc.select()).fetchall(), [(1,
            None)])

    def test_engine_level_options(self):
        eng = engines.testing_engine(options={'execution_options'
                : {'foo': 'bar'}})
        conn = eng.contextual_connect()
        eq_(conn._execution_options['foo'], 'bar')
        eq_(conn.execution_options(bat='hoho')._execution_options['foo'
            ], 'bar')
        eq_(conn.execution_options(bat='hoho')._execution_options['bat'
            ], 'hoho')
        eq_(conn.execution_options(foo='hoho')._execution_options['foo'
            ], 'hoho')
        eng.update_execution_options(foo='hoho')
        conn = eng.contextual_connect()
        eq_(conn._execution_options['foo'], 'hoho')
        

class CompiledCacheTest(TestBase):
    @classmethod
    def setup_class(cls):
        global users, metadata
        metadata = MetaData(testing.db)
        users = Table('users', metadata,
            Column('user_id', INT, primary_key=True,
                            test_needs_autoincrement=True),
            Column('user_name', VARCHAR(20)),
        )
        metadata.create_all()

    @engines.close_first
    def teardown(self):
        testing.db.connect().execute(users.delete())
        
    @classmethod
    def teardown_class(cls):
        metadata.drop_all()
    
    def test_cache(self):
        conn = testing.db.connect()
        cache = {}
        cached_conn = conn.execution_options(compiled_cache=cache)
        
        ins = users.insert()
        cached_conn.execute(ins, {'user_name':'u1'})
        cached_conn.execute(ins, {'user_name':'u2'})
        cached_conn.execute(ins, {'user_name':'u3'})
        assert len(cache) == 1
        eq_(conn.execute("select count(*) from users").scalar(), 3)
    
class LoggingNameTest(TestBase):
    def _assert_names_in_execute(self, eng, eng_name, pool_name):
        eng.execute(select([1]))
        for name in [b.name for b in self.buf.buffer]:
            assert name in (
                'sqlalchemy.engine.base.Engine.%s' % eng_name,
                'sqlalchemy.pool.%s.%s' % 
                    (eng.pool.__class__.__name__, pool_name)
            )

    def _assert_no_name_in_execute(self, eng):
        eng.execute(select([1]))
        for name in [b.name for b in self.buf.buffer]:
            assert name in (
                'sqlalchemy.engine.base.Engine',
                'sqlalchemy.pool.%s' % eng.pool.__class__.__name__
            )
    
    def _named_engine(self, **kw):
        options = {
            'logging_name':'myenginename',
            'pool_logging_name':'mypoolname'
        }
        options.update(kw)
        return engines.testing_engine(options=options)

    def _unnamed_engine(self, **kw):
        return engines.testing_engine(options=kw)

    def setup(self):
        self.buf = logging.handlers.BufferingHandler(100)
        for log in [
            logging.getLogger('sqlalchemy.engine'),
            logging.getLogger('sqlalchemy.pool')
        ]:
            log.addHandler(self.buf)

    def teardown(self):
        for log in [
            logging.getLogger('sqlalchemy.engine'),
            logging.getLogger('sqlalchemy.pool')
        ]:
            log.removeHandler(self.buf)
        
    def test_named_logger_names(self):
        eng = self._named_engine()
        eq_(eng.logging_name, "myenginename")
        eq_(eng.pool.logging_name, "mypoolname")
        
    def test_named_logger_names_after_dispose(self):
        eng = self._named_engine()
        eng.execute(select([1]))
        eng.dispose()
        eq_(eng.logging_name, "myenginename")
        eq_(eng.pool.logging_name, "mypoolname")
    
    def test_unnamed_logger_names(self):
        eng = self._unnamed_engine()
        eq_(eng.logging_name, None)
        eq_(eng.pool.logging_name, None)
    
    def test_named_logger_execute(self):
        eng = self._named_engine()
        self._assert_names_in_execute(eng, "myenginename", "mypoolname")

    def test_named_logger_echoflags_execute(self):
        eng = self._named_engine(echo='debug', echo_pool='debug')
        self._assert_names_in_execute(eng, "myenginename", "mypoolname")

    def test_named_logger_execute_after_dispose(self):
        eng = self._named_engine()
        eng.execute(select([1]))
        eng.dispose()
        self._assert_names_in_execute(eng, "myenginename", "mypoolname")

    def test_unnamed_logger_execute(self):
        eng = self._unnamed_engine()
        self._assert_no_name_in_execute(eng)

    def test_unnamed_logger_echoflags_execute(self):
        eng = self._unnamed_engine(echo='debug', echo_pool='debug')
        self._assert_no_name_in_execute(eng)

class EchoTest(TestBase):
    
    def setup(self):
        self.level = logging.getLogger('sqlalchemy.engine').level
        logging.getLogger('sqlalchemy.engine').setLevel(logging.WARN)
        self.buf = logging.handlers.BufferingHandler(100)
        logging.getLogger('sqlalchemy.engine').addHandler(self.buf)
    
    def teardown(self):
        logging.getLogger('sqlalchemy.engine').removeHandler(self.buf)
        logging.getLogger('sqlalchemy.engine').setLevel(self.level)
    
    def testing_engine(self):
        e = engines.testing_engine()
        
        # do an initial execute to clear out 'first connect'
        # messages
        e.execute("select 10")
        self.buf.flush()
        
        return e
        
    def test_levels(self):
        e1 = engines.testing_engine()

        eq_(e1._should_log_info(), False)
        eq_(e1._should_log_debug(), False)
        eq_(e1.logger.isEnabledFor(logging.INFO), False)
        eq_(e1.logger.getEffectiveLevel(), logging.WARN)

        e1.echo = True
        eq_(e1._should_log_info(), True)
        eq_(e1._should_log_debug(), False)
        eq_(e1.logger.isEnabledFor(logging.INFO), True)
        eq_(e1.logger.getEffectiveLevel(), logging.INFO)

        e1.echo = 'debug'
        eq_(e1._should_log_info(), True)
        eq_(e1._should_log_debug(), True)
        eq_(e1.logger.isEnabledFor(logging.DEBUG), True)
        eq_(e1.logger.getEffectiveLevel(), logging.DEBUG)
        
        e1.echo = False
        eq_(e1._should_log_info(), False)
        eq_(e1._should_log_debug(), False)
        eq_(e1.logger.isEnabledFor(logging.INFO), False)
        eq_(e1.logger.getEffectiveLevel(), logging.WARN)
        
    def test_echo_flag_independence(self):
        """test the echo flag's independence to a specific engine."""

        e1 = self.testing_engine()
        e2 = self.testing_engine()
        
        e1.echo = True
        e1.execute(select([1]))
        e2.execute(select([2]))
        
        e1.echo = False
        e1.execute(select([3]))
        e2.execute(select([4]))
        
        e2.echo = True
        e1.execute(select([5]))
        e2.execute(select([6]))
        
        assert self.buf.buffer[0].getMessage().startswith("SELECT 1")
        assert self.buf.buffer[2].getMessage().startswith("SELECT 6")
        assert len(self.buf.buffer) == 4
    
class ResultProxyTest(TestBase):
    def test_nontuple_row(self):
        """ensure the C version of BaseRowProxy handles 
        duck-type-dependent rows."""
        
        from sqlalchemy.engine import RowProxy

        class MyList(object):
            def __init__(self, l):
                self.l = l

            def __len__(self):
                return len(self.l)

            def __getitem__(self, i):
                return list.__getitem__(self.l, i)

        proxy = RowProxy(object(), MyList(['value']), [None], {'key'
                         : (None, 0), 0: (None, 0)})
        eq_(list(proxy), ['value'])
        eq_(proxy[0], 'value')
        eq_(proxy['key'], 'value')

    @testing.provide_metadata
    def test_no_rowcount_on_selects_inserts(self):
        """assert that rowcount is only called on deletes and updates.

        This because cursor.rowcount can be expensive on some dialects
        such as Firebird.

        """

        engine = engines.testing_engine()
        metadata.bind = engine
        
        t = Table('t1', metadata,
            Column('data', String(10))
        )
        metadata.create_all()

        class BreakRowcountMixin(object):
            @property
            def rowcount(self):
                assert False
        
        execution_ctx_cls = engine.dialect.execution_ctx_cls
        engine.dialect.execution_ctx_cls = type("FakeCtx", 
                                            (BreakRowcountMixin, 
                                            execution_ctx_cls), 
                                            {})

        try:
            r = t.insert().execute({'data': 'd1'}, {'data': 'd2'},
                                   {'data': 'd3'})
            eq_(t.select().execute().fetchall(), [('d1', ), ('d2', ),
                ('d3', )])
            assert_raises(AssertionError, t.update().execute, {'data'
                          : 'd4'})
            assert_raises(AssertionError, t.delete().execute)
        finally:
            engine.dialect.execution_ctx_cls = execution_ctx_cls
    
    @testing.requires.python26
    def test_rowproxy_is_sequence(self):
        import collections
        from sqlalchemy.engine import RowProxy

        row = RowProxy(object(), ['value'], [None], {'key'
                         : (None, 0), 0: (None, 0)})
        assert isinstance(row, collections.Sequence)
    
    @testing.requires.cextensions
    def test_row_c_sequence_check(self):
        import csv
        import collections
        from StringIO import StringIO
        
        metadata = MetaData()
        metadata.bind = 'sqlite://'
        users = Table('users', metadata,
            Column('id', Integer, primary_key=True),
            Column('name', String(40)),
        )
        users.create()

        users.insert().execute(name='Test')
        row = users.select().execute().fetchone()

        s = StringIO()
        writer = csv.writer(s)
        # csv performs PySequenceCheck call
        writer.writerow(row)
        assert s.getvalue().strip() == '1,Test'
        
class ProxyConnectionTest(TestBase):

    @testing.fails_on('firebird', 'Data type unknown')
    def test_proxy(self):
        
        stmts = []
        cursor_stmts = []
        
        class MyProxy(ConnectionProxy):
            def execute(
                self,
                conn,
                execute,
                clauseelement,
                *multiparams,
                **params
                ):
                stmts.append((str(clauseelement), params, multiparams))
                return execute(clauseelement, *multiparams, **params)

            def cursor_execute(
                self,
                execute,
                cursor,
                statement,
                parameters,
                context,
                executemany,
                ):
                cursor_stmts.append((str(statement), parameters, None))
                return execute(cursor, statement, parameters, context)
        
        def assert_stmts(expected, received):
            for stmt, params, posn in expected:
                if not received:
                    assert False
                while received:
                    teststmt, testparams, testmultiparams = \
                        received.pop(0)
                    teststmt = re.compile(r'[\n\t ]+', re.M).sub(' ',
                            teststmt).strip()
                    if teststmt.startswith(stmt) and (testparams
                            == params or testparams == posn):
                        break

        for engine in \
            engines.testing_engine(options=dict(implicit_returning=False,
                                   proxy=MyProxy())), \
            engines.testing_engine(options=dict(implicit_returning=False,
                                   proxy=MyProxy(),
                                   strategy='threadlocal')):
            m = MetaData(engine)
            t1 = Table('t1', m, 
                Column('c1', Integer, primary_key=True), 
                Column('c2', String(50), default=func.lower('Foo'),
                                            primary_key=True)
            )
            m.create_all()
            try:
                t1.insert().execute(c1=5, c2='some data')
                t1.insert().execute(c1=6)
                eq_(engine.execute('select * from t1').fetchall(), [(5,
                    'some data'), (6, 'foo')])
            finally:
                m.drop_all()
            engine.dispose()
            compiled = [('CREATE TABLE t1', {}, None),
                        ('INSERT INTO t1 (c1, c2)', {'c2': 'some data',
                        'c1': 5}, None), ('INSERT INTO t1 (c1, c2)',
                        {'c1': 6}, None), ('select * from t1', {},
                        None), ('DROP TABLE t1', {}, None)]
            if not testing.against('oracle+zxjdbc'):  # or engine.dialect.pr
                                                      # eexecute_pk_sequence
                                                      # s:
                cursor = [
                    ('CREATE TABLE t1', {}, ()),
                    ('INSERT INTO t1 (c1, c2)', {'c2': 'some data', 'c1'
                     : 5}, (5, 'some data')),
                    ('SELECT lower', {'lower_2': 'Foo'}, ('Foo', )),
                    ('INSERT INTO t1 (c1, c2)', {'c2': 'foo', 'c1': 6},
                     (6, 'foo')),
                    ('select * from t1', {}, ()),
                    ('DROP TABLE t1', {}, ()),
                    ]
            else:
                insert2_params = 6, 'Foo'
                if testing.against('oracle+zxjdbc'):
                    insert2_params += (ReturningParam(12), )
                cursor = [('CREATE TABLE t1', {}, ()),
                          ('INSERT INTO t1 (c1, c2)', {'c2': 'some data'
                          , 'c1': 5}, (5, 'some data')),
                          ('INSERT INTO t1 (c1, c2)', {'c1': 6,
                          'lower_2': 'Foo'}, insert2_params),
                          ('select * from t1', {}, ()), ('DROP TABLE t1'
                          , {}, ())]  # bind param name 'lower_2' might
                                      # be incorrect
            assert_stmts(compiled, stmts)
            assert_stmts(cursor, cursor_stmts)
    
    def test_options(self):
        track = []
        class TrackProxy(ConnectionProxy):
            def __getattribute__(self, key):
                fn = object.__getattribute__(self, key)
                def go(*arg, **kw):
                    track.append(fn.__name__)
                    return fn(*arg, **kw)
                return go
        engine = engines.testing_engine(options={'proxy':TrackProxy()})
        conn = engine.connect()
        c2 = conn.execution_options(foo='bar')
        eq_(c2._execution_options, {'foo':'bar'})
        c2.execute(select([1]))
        c3 = c2.execution_options(bar='bat')
        eq_(c3._execution_options, {'foo':'bar', 'bar':'bat'})
        eq_(track, ['execute', 'cursor_execute'])
        
        
    def test_transactional(self):
        track = []
        class TrackProxy(ConnectionProxy):
            def __getattribute__(self, key):
                fn = object.__getattribute__(self, key)
                def go(*arg, **kw):
                    track.append(fn.__name__)
                    return fn(*arg, **kw)
                return go

        engine = engines.testing_engine(options={'proxy':TrackProxy()})
        conn = engine.connect()
        trans = conn.begin()
        conn.execute(select([1]))
        trans.rollback()
        trans = conn.begin()
        conn.execute(select([1]))
        trans.commit()
        
        eq_(track, [
            'begin',
            'execute',
            'cursor_execute',
            'rollback',
            'begin',
            'execute',
            'cursor_execute',
            'commit',
            ])
        
    @testing.requires.savepoints
    @testing.requires.two_phase_transactions
    def test_transactional_advanced(self):
        track = []
        class TrackProxy(ConnectionProxy):
            def __getattribute__(self, key):
                fn = object.__getattribute__(self, key)
                def go(*arg, **kw):
                    track.append(fn.__name__)
                    return fn(*arg, **kw)
                return go

        engine = engines.testing_engine(options={'proxy':TrackProxy()})
        conn = engine.connect()
        
        trans = conn.begin()
        trans2 = conn.begin_nested()
        conn.execute(select([1]))
        trans2.rollback()
        trans2 = conn.begin_nested()
        conn.execute(select([1]))
        trans2.commit()
        trans.rollback()
        
        trans = conn.begin_twophase()
        conn.execute(select([1]))
        trans.prepare()
        trans.commit()

        track = [t for t in track if t not in ('cursor_execute', 'execute')]
        eq_(track, ['begin', 'savepoint', 
                    'rollback_savepoint', 'savepoint', 'release_savepoint',
                    'rollback', 'begin_twophase', 
                       'prepare_twophase', 'commit_twophase']
        )

