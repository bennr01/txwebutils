"""
Cookie implementations for L{txwebutils.csauth}.
"""
from zope.interface import implementer
from twisted.python.components import registerAdapter
from twisted.web.server import Session

from .icsauth import ILoginCookie


@implementer(ILoginCookie)
class LoginCookie(object):
    
    __slots__ = ("userdata", )
    
    def __init__(self, session):
        self.userdata = None

registerAdapter(LoginCookie, Session, ILoginCookie)
