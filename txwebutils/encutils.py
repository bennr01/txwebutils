"""
Encoding utilities for twisted web.

@var DEFAULT_SERVER_ENCODING: the default encoding for the response
@type DEFAULT_SERVER_ENCODING: L{str}
@var DEFAULT_CLIENT_ENCODING: the default encoding for the request
@type DEFAULT_CLIENT_ENCODING: L{str}
@var HEADER_ENCODING: Encoding to use to decode/encode the encoding related headers
@type HEADER_ENCODING: L{str}
@var CHARSET_SUB_PATTERN: charset regex substitution pattern
@type CHARSET_SUB_PATTERN: L{str}
@var CHARSET_SEARCH_PATTERN: charset regex search pattern
"""

import re
from functools import wraps

import six
from twisted.internet import defer
from twisted.web import server


DEFAULT_SERVER_ENCODING = u"UTF-8"
DEFAULT_CLIENT_ENCODING =u"UTF-8"  # u"latin-1"
HEADER_ENCODING = u"ascii"
CHARSET_SUB_PATTERN = re.compile(b"charset=.*(;|\\Z)")
CHARSET_SEARCH_PATTERN = CHARSET_SUB_PATTERN


def get_response_encoding(request):
    """
    Return the encoding which will be used for the response.
    
    @param request: request for which response to get the encoding for
    @type request: L{twisted.web.server.Request}
    @return: encoding to used for the response
    @rtype: L{six.text_type}
    """
    headers = request.getAllHeaders()
    ac_header = headers.get(b"accept-charset", None)
    if (ac_header is not None) and (len(ac_header) > 0):
        ac_header = ac_header.decode(HEADER_ENCODING)
        values = [v.split(u";") for v in ac_header.replace(u" ", u"").split(u",")]
        values = [(float(v[1]), v[0]) if len(v) > 1 else (1.0, v[0]) for v in values]
        ordered = [v[1] for v in sorted(values)]
        prime = ordered[0]
        if prime == u"*":
            return DEFAULT_SERVER_ENCODING
        return prime
    else:
        return DEFAULT_SERVER_ENCODING


def get_request_encoding(request):
    """
    Return the encoding which will be used for decoding the request.
    
    @param request: request to get the encoding for
    @type request: L{twisted.web.server.Request}
    @return: the encoding used by the request
    @rtype: L{six.text_type}
    """
    headers = request.getAllHeaders()
    # check 'accept-charset' header first
    #ac_header = headers.get(b"accept-charset", None)
    #if (ac_header is not None) and (len(ac_header) > 0):
    #    ac_header = ac_header.decode(HEADER_ENCODING)
    #    values = [v.split(u";") for v in ac_header.replace(u" ", u"").split(u",")]
    #    values = [(float(v[1]), v[0]) if len(v) > 1 else (1.0, v[0]) for v in values]
    #    ordered = [v[1] for v in sorted(values)]
    #    return ordered[0]
    header = headers.get(b"Content-Type", None)
    if (header is None) or (b"charset=" not in header):
        return DEFAULT_CLIENT_ENCODING
    else:
        header = header.decode(HEADER_ENCODING)
        result = CHARSET_SEARCH_PATTERN.search(header)
        if result is None:
            return DEFAULT_CLIENT_ENCODING
        ss = header[result.start(): result.end()]
        return ss[ss.find(u"="):-1]


def set_response_encoding(request, encoding):
    """
    Set the encoding in the header for request.
    
    @param request: request to set the encoding for
    @type request: L{twisted.web.server.Request}
    @param encoding: encoding to set
    @type encoding: L{six.binary_type}
    """
    if isinstance(encoding, six.text_type):
        encoding = encoding.encode(HEADER_ENCODING)
    elif not isinstance(header, six.binary_type):
        raise TypeError("Got non-string type value: {}".format(repr(header)))
    header = request.getHeader(b"Content-Type")
    if header is None:
        # create new header
        new_header = b"text/html; charset=" + encoding
    elif b"charset=" in header:
        # replace charset
        new_header = CHARSET_SUB_PATTERN.sub(b"charset=" + encoding + b";", header)
        if new_header.endswith(b";"):
            new_header = new_header[:-1]
    elif b"text/" not in header:
        # encodings are only useful for text/* content-types
        # other possible values are bytes, map and stream
        # if the above condition evaluates to true, chances are that we need to completely
        # replace the content-type header.
        new_header = b"text/html; charset=" + encoding
    else:
        # append charset
        new_header = header + b"; charset=" + encoding
    request.setHeader(b"Content-Type", new_header)


def _gotrender(request, response):
    """
    This function will be called when an L{unicode_response} decorated function returns.
    
    @param request: request which is currently being processed
    @type request: L{twisted.web.server.Request}
    @param response: the generated response
    @type response: L{six.binary_type} or L{six.text_type}
    """
    if isinstance(response, six.binary_type):
        request.write(response)
        request.finish()
    elif isinstance(response, six.text_type):
        encoding = get_response_encoding(request)
        set_response_encoding(request, encoding)
        request.write(response.encode(encoding))
        request.finish()
    else:
        raise TypeError("Resource returned unknown type '{ty}'; expected '{t}' or '{b}'".format(ty=type(response), t=six.text_type, b=six.binary_type))


def unicode_response(f):
    """
    Decorator for indicating that a twisted.web.resource.Resource.render_*() method returns unicode or a deferred.
    
    @param f: function to decorate
    @type f: callable
    @return: decorated function
    @rtype: callable
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if isinstance(args[0],  server.Request) or len(args) == 0:
            # function
            request = args[0]
        else:
            # method (args[0] is self)
            request = args[1]
        d = defer.maybeDeferred(f, *args, **kwargs)
        d.addCallback(lambda response: _gotrender(request, response))
        d.addErrback(request.processingFailed)
        return server.NOT_DONE_YET
    return wrapper


def get_unicode_params(request, encoding=None):
    """
    Return the uncode parameters of the given request.
    
    @param request: request to get the unicode param for
    @type request: L{twisted.web.server.Request}
    @param encoding: the encoding to use. Default: try to auto-determine encoding, falling back to Latin-1.s
    @type encoding: L{six.text_type}
    @return: the unicode params of this request
    @rtype: L{dict} of {L{six.text_type}: L{six.text_type}}
    """
    if encoding is None:
        encoding = get_request_encoding(request)
    ret = {}
    for key in request.args:
        ret[key.decode(encoding)] = [e.decode(encoding) for e in request.args[key]]
    return ret
