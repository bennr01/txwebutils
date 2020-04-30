# -*- coding: utf-8 -*-
"""
Tests for L{txwebutils.encutils}.
"""
import json

import six
from twisted.internet import defer, reactor
from twisted.web.resource import Resource, NoResource
from twisted.trial import unittest

from treq.testing import StubTreq

from txwebutils.encutils import unicode_response, get_response_encoding, get_unicode_params


class TestRootResource(Resource):
    """
    The root resource for this test.
    """
    isLeaf = False
    
    def getChild(self, name, request):
        name = name.replace(b"/", b"")
        if name == b"defer-binary":
            return TestDeferBinaryResource()
        elif name == b"defer-unicode":
            return TestDeferUnicodeResource()
        elif name == b"binary":
            return TestBinaryResource()
        elif name == b"unicode":
            return TestUnicodeResource()
        elif name == b"unicode-ex":
            return TestUnicodeExResource()
        elif name == b"get-encoding":
            return TestGetEncodingResource()
        elif name == b"get-unicode-params":
            return TestGetUnicodeParamsResource()
        else:
            return NoResource()


class TestBinaryResource(Resource):
    """
    Test resource rendering to a binary string.
    """
    isLeaf = True
    
    @unicode_response
    def render_GET(self, request):
        return b"binary_string"


class TestDeferBinaryResource(Resource):
    """
    Test resource rendering to a deferred binary string.
    """
    isLeaf = True
    
    @unicode_response
    def render_GET(self, request):
        return defer.succeed(b"binary_string")


class TestUnicodeResource(Resource):
    """
    Test resource rendering to a unicode string.
    """
    isLeaf = True
    
    @unicode_response
    def render_GET(self, request):
        return u"unicode_string"


class TestUnicodeExResource(Resource):
    """
    Test resource rendering to a unicode string with non-ascii characters.
    """
    isLeaf = True
    
    @unicode_response
    def render_GET(self, request):
        return u"umlaute: äöüß"

class TestDeferUnicodeResource(Resource):
    """
    Test resource rendering to a deferred unicode string.
    """
    isLeaf = True
    
    @unicode_response
    def render_GET(self, request):
        return defer.succeed(u"unicode_string")


class TestGetEncodingResource(Resource):
    """
    Test resource responding with the encoding of the request.
    """
    isLeaf = True
    
    @unicode_response
    def render_GET(self, request):
        return get_response_encoding(request)


class TestGetUnicodeParamsResource(Resource):
    """
    Test resource responding with the unicode params of the request.
    """
    isLeaf = True
    
    @unicode_response
    def render_GET(self, request):
        params = get_unicode_params(request)
        return json.dumps(params)
        
                
class EncutilsTests(unittest.TestCase):
    """
    The tests for L{txwebutils.encutils}.
    """
    def get_resource(self):
        return TestRootResource()
    
    @defer.inlineCallbacks
    def test_binary(self):
        """
        Test a binary response.
        """
        treq = StubTreq(self.get_resource())
        r = yield treq.get("http://localhost:8080/binary")
        self.assertEqual(r.code, 200)
        c = yield r.content()
        self.assertIsInstance(c, six.binary_type)
        self.assertEqual(c, b"binary_string")
    
    @defer.inlineCallbacks
    def test_unicode_decode(self):
        """
        Test a unicode response decoding.
        """
        treq = StubTreq(self.get_resource())
        r = yield treq.get("http://localhost:8080/unicode")
        self.assertEqual(r.code, 200)
        c = yield r.text()
        self.assertIsInstance(c, six.text_type)
        self.assertEqual(c, u"unicode_string")
    
    @defer.inlineCallbacks
    def test_unicode_decode_raw(self):
        """
        Test a unicode response without decoding.
        """
        treq = StubTreq(self.get_resource())
        r = yield treq.get("http://localhost:8080/unicode")
        self.assertEqual(r.code, 200)
        c = yield r.content()
        self.assertIsInstance(c, six.binary_type)
        self.assertEqual(c, b"unicode_string")
    
    
    @defer.inlineCallbacks
    def test_unicode_decode_ex(self):
        """
        Test a unicode response with non-ascii characters and various
        encodings.
        """
        treq = StubTreq(self.get_resource())
        encodings = [b"utf-8", b"latin-1", b"cp500", b"iso-8859-2"]
        for encoding in encodings:
            headers = {b"Accept-Charset": encoding}
            r = yield treq.get("http://localhost:8080/unicode-ex", headers=headers)
            self.assertEqual(r.code, 200)
            self.assertIn(encoding.decode(u"ascii"), r.headers.getRawHeaders("Content-Type", [None])[0])
            c = yield r.text(encoding=encoding)
            self.assertIsInstance(c, six.text_type)
            self.assertEqual(c, u"umlaute: äöüß")
    
    @defer.inlineCallbacks
    def test_binary_deferred(self):
        """
        Test a binary response with a deferred result.
        """
        treq = StubTreq(self.get_resource())
        r = yield treq.get("http://localhost:8080/defer-binary")
        self.assertEqual(r.code, 200)
        c = yield r.content()
        self.assertIsInstance(c, six.binary_type)
        self.assertEqual(c, b"binary_string")
    
    @defer.inlineCallbacks
    def test_unicode_deferred(self):
        """
        Test a unicode response with a deferred result.
        """
        treq = StubTreq(self.get_resource())
        r = yield treq.get("http://localhost:8080/defer-unicode")
        self.assertEqual(r.code, 200)
        c = yield r.text()
        self.assertIsInstance(c, six.text_type)
        self.assertEqual(c, u"unicode_string")
    
    @defer.inlineCallbacks
    def test_get_response_encoding(self):
        """
        Test L{txwebutils.encutils.get_response_encoding}.
        """
        treq = StubTreq(self.get_resource())
        encodings = [b"utf-8", b"latin-1", b"cp500", b"iso-8859-2"]
        for encoding in encodings:
            headers = {b"Accept-Charset": encoding}
            r = yield treq.get("http://localhost:8080/get-encoding", headers=headers)
            self.assertEqual(r.code, 200)
            self.assertIn(encoding.decode(u"ascii"), r.headers.getRawHeaders("Content-Type", [None])[0])
            c = yield r.text(encoding=encoding)
            self.assertIsInstance(c, six.text_type)
            self.assertEqual(c, encoding.decode("ascii"))
        
    @defer.inlineCallbacks
    def test_unicode_params(self):
        """
        Test L{txwebutils.encutils.get_unicode_params}.
        """
        treq = StubTreq(self.get_resource())
        encodings = [b"utf-8", b"latin-1", b"cp500", b"iso-8859-2"]
        for encoding in encodings:
            headers = {b"Accept-Charset": encoding}
            params = {u"test": [u"value"], u"uml": [u"äöüß"], u"multi": [u"v1", u"v2"]}
            r = yield treq.get("http://localhost:8080/get-unicode-params", headers=headers, params=params)
            self.assertEqual(r.code, 200)
            c = yield r.json(encoding=encoding)
            self.assertIsInstance(c[u"test"][0], six.text_type)
            self.assertIsInstance(c[u"uml"][0], six.text_type)
            self.assertEqual(c, params)

