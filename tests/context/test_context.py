# Copyright 2014-2015 Canonical Limited.
#
# This file is part of charm-helpers.
#
# charm-helpers is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3 as
# published by the Free Software Foundation.
#
# charm-helpers is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with charm-helpers.  If not, see <http://www.gnu.org/licenses/>.
import unittest
from mock import patch, sentinel
import six

from charmhelpers import context
from charmhelpers.core import hookenv


class TestRelations(unittest.TestCase):
    def setUp(self):
        def install(*args, **kw):
            p = patch.object(*args, **kw)
            p.start()
            self.addCleanup(p.stop)

        install(hookenv, 'relation_types', return_value=['rel', 'pear'])
        install(hookenv, 'peer_relation_id', return_value='pear:9')
        install(hookenv, 'relation_ids',
                side_effect=lambda x: ['{}:{}'.format(x, i)
                                       for i in range(9, 11)])
        install(hookenv, 'related_units',
                side_effect=lambda x: ['svc_' + x.replace(':', '/')])
        install(hookenv, 'local_unit', return_value='foo/1')
        install(hookenv, 'relation_get')
        install(hookenv, 'relation_set')
        # install(hookenv, 'is_leader', return_value=False)

    def test_relations(self):
        rels = context.Relations()
        self.assertListEqual(list(rels.keys()),
                             ['pear', 'rel'])  # Ordered alphabetically
        self.assertListEqual(list(rels['rel'].keys()),
                             ['rel:9', 'rel:10'])  # Ordered numerically

        # Relation data is loaded on demand, not on instantiation.
        self.assertFalse(hookenv.relation_get.called)

        # But we did have to retrieve some lists of units etc.
        self.assertGreaterEqual(hookenv.relation_ids.call_count, 2)
        self.assertGreaterEqual(hookenv.related_units.call_count, 2)

    def test_relation(self):
        rel = context.Relations()['rel']['rel:9']
        self.assertEqual(rel.relid, 'rel:9')
        self.assertEqual(rel.relname, 'rel')
        self.assertEqual(rel.service, 'svc_rel')
        self.assertTrue(isinstance(rel.local, context.RelationInfo))
        self.assertEqual(rel.local.unit, hookenv.local_unit())
        self.assertTrue(isinstance(rel.peers, context.OrderedDict))
        self.assertTrue(len(rel.peers), 2)
        self.assertTrue(isinstance(rel.peers['svc_pear/9'],
                                   context.RelationInfo))

        # I use this in my log messages. Relation id for identity
        # plus service name for ease of reference.
        self.assertEqual(str(rel), 'rel:9 (svc_rel)')

    def test_relation_no_peer_relation(self):
        hookenv.peer_relation_id.return_value = None
        rel = context.Relation('rel:10')
        self.assertTrue(rel.peers is None)

    def test_relation_no_peers(self):
        hookenv.related_units.side_effect = None
        hookenv.related_units.return_value = []
        rel = context.Relation('rel:10')
        self.assertDictEqual(rel.peers, {})

    def test_relationinfo(self):
        hookenv.relation_get.return_value = {sentinel.key: 'value'}
        r = context.RelationInfo('rel:10', 'svc_rel/9')

        self.assertEqual(r.relname, 'rel')
        self.assertEqual(r.relid, 'rel:10')
        self.assertEqual(r.unit, 'svc_rel/9')
        self.assertEqual(r.service, 'svc_rel')
        self.assertEqual(r.number, 9)

        self.assertFalse(hookenv.relation_get.called)
        self.assertEqual(r[sentinel.key], 'value')
        hookenv.relation_get.assert_has_call(unit='svc_rel/9', rid='rel:10')

        # Updates fail
        with self.assertRaises(TypeError):
            r['newkey'] = 'foo'

        # Deletes fail
        with self.assertRaises(TypeError):
            del r[sentinel.key]

        # I use this for logging.
        self.assertEqual(str(r), 'rel:10 (svc_rel/9)')

    def test_relationinfo_local(self):
        r = context.RelationInfo('rel:10', hookenv.local_unit())

        # Updates work, with standard strings.
        r[sentinel.key] = 'value'
        hookenv.relation_set.assert_called_once_with(
            'rel:10', {sentinel.key: 'value'})

        # Python 2 unicode strings work too.
        hookenv.relation_set.reset_mock()
        r[sentinel.key] = six.u('value')
        hookenv.relation_set.assert_called_once_with(
            'rel:10', {sentinel.key: six.u('value')})

        # Byte strings fail under Python 3.
        if six.PY3:
            with self.assertRaises(ValueError):
                r[sentinel.key] = six.b('value')

        # Deletes work
        del r[sentinel.key]
        hookenv.relation_set.assert_has_call('rel:10', {sentinel.key: None})

        # Attempting to write a non-string fails
        with self.assertRaises(ValueError):
            r[sentinel.key] = 42


class TestLeader(unittest.TestCase):
    @patch.object(hookenv, 'leader_get')
    def test_get(self, leader_get):
        leader_get.return_value = {'a_key': 'a_value'}

        leader = context.Leader()
        self.assertEqual(leader['a_key'], 'a_value')
        leader_get.assert_has_call()

        with self.assertRaises(KeyError):
            leader['missing']

    @patch.object(hookenv, 'leader_set')
    @patch.object(hookenv, 'leader_get')
    @patch.object(hookenv, 'is_leader')
    def test_set(self, is_leader, leader_get, leader_set):
        is_leader.return_value = True
        leader = context.Leader()

        # Updates work
        leader[sentinel.key] = 'foo'
        leader_set.assert_has_call({sentinel.key: 'foo'})
        del leader[sentinel.key]
        leader_set.assert_has_call({sentinel.key: None})

        # Python 2 unicode string values work too
        leader[sentinel.key] = six.u('bar')
        leader_set.assert_has_call({sentinel.key: 'bar'})

        # Byte strings fail under Python 3
        if six.PY3:
            with self.assertRaises(ValueError):
                leader[sentinel.key] = six.b('baz')

        # Non strings fail, as implicit casting causes more trouble
        # than it solves. Simple types like integers would round trip
        # back as strings.
        with self.assertRaises(ValueError):
            leader[sentinel.key] = 42

    @patch.object(hookenv, 'leader_set')
    @patch.object(hookenv, 'leader_get')
    @patch.object(hookenv, 'is_leader')
    def test_set_not_leader(self, is_leader, leader_get, leader_set):
        is_leader.return_value = False
        leader_get.return_value = {'a_key': 'a_value'}
        leader = context.Leader()
        with self.assertRaises(TypeError):
            leader['a_key'] = 'foo'
        with self.assertRaises(TypeError):
            del leader['a_key']
