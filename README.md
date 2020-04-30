# txwebutils - utilities for `twisted.web`

[![PyPI version](https://badge.fury.io/py/txwebutils.svg)](https://badge.fury.io/py/txwebutils) [![Build Status](https://travis-ci.org/bennr01/txwebutils.svg?branch=master)](https://travis-ci.org/bennr01/txwebutils) [![GitHub license](https://img.shields.io/github/license/Naereen/StrapDown.js.svg)](https://github.com/Naereen/StrapDown.js/blob/master/LICENSE)

## What is `txwebutils`?

`txwebutils` is a pure-python library containing various utility functions and implementations for the `twisted.web` web framework. It is the result of combining useful code from my various other projects.

## Features

- support for unicode string results for `twisted.web.resource.Resource.render_*` methods.
- support for deferreds results for `twisted.web.resource.Resource.render_*`.
- utility functions to get the URL parameters in unicode.
- A custom cross-site authentication implementation using `twisted.cred`.

## Examples

```python
# -*- coding: utf-8 -*-
"""
Example for @unicode_response.

The @unicode_response decorator allows both unicode and/or deferred results in render_* methods.
"""
from twisted.internet import defer
from twisted.web.resource import Resource
from txwebutils import unicode_response


class UnicodeRespondingResource(Resource):
    """
    This resource serves a unicode string on a GET request.
    
    @unicode_response tries its best to guess the encoding correctly.
    """
    @unicode_response
    def render_GET(self, request):
        return u"This is a unicode string: äöüß"

class BinaryRespondingResource(Resource):
    """
    This resource serves a binary string on a GET request.
    This shows that you can return whatever string type you desire.
    """
    @unicode_response
    def render_GET(self, request):
        return b"This is a binary string"

class DeferredResultingResource(Resource)
	"""
    This resource serves a deferred which fires with a unicode string on a GET request.
    """
    @unicode_response
    def render_GET(self, request):
        return defer.succeed(u"This is a unicode string: äöüß")
    
class InlineCallbacksResource(Resource)
	"""
    This resource uses 'twisted.internet.defer.inlineCallbacks'
    """
    @unicode_response
    @defer.inlineCallbacks
    def render_GET(self, request):
        s = yield defer.succeed(u"This is a unicode string: äöüß")
        defer.returnValue(s)
```

