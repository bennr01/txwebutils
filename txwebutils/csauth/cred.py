"""
Credential interface implementations for L{txwebutils.csauth}.
"""
import six
from twisted.cred.checkers import ICredentialsChecker
from twisted.internet import defer
from twisted.cred.error import UnauthorizedLogin
from zope.interface import Interface, implementer

from .icsauth import IUnicodeUsernamePassword


@implementer(IUnicodeUsernamePassword)
class UnicodeUsernamePassword(object):
    """
    Implementation of L{txwebutils.csauth.itxcsauth.IUnicodeUsernamePassword}.
    """
    
    def __init__(self, username, password):
        self.username = username
        self.password = password
    
    def checkPassword(password):
        return (password == self.password)


@implementer(ICredentialsChecker)
class InMemoryUnicodeUsernamePasswordDatabase(object):
    """
    In memory credentials checker for L{UnicodeUsernamePassword}.
    
    Do not use this for your applications.
    
    Also, please note that L{requestAvatarId} must return a binary string.
    
    @param passwords: a dict mapping the usernames to their passwords
    @type passwords: L{dict} of L{str} -> L{str}
    """
    credentialInterfaces = [IUnicodeUsernamePassword]
    
    def __init__(self, passwords=None):
        if passwords is not None:
            self._passwords = passwords
        else:
            self._passwords = {}
    
    def addUser(self, username, password):
        """
        Add a username/password to the database.
        
        @param username: username to add
        @type username: L{six.text_type}
        @param password: password for user
        @type password: L{six.text_type}
        """
        assert isinstance(username, six.text_type)
        assert isinstance(password, six.text_type)
        assert username not in self._passwords
        self._passwords[username] = password
    
    def requestAvatarId(self, credentials):
        if IUnicodeUsernamePassword.providedBy(credentials):
            if credentials.username not in self._passwords:
                return defer.fail(UnauthorizedLogin("User not found!"))
            elif credentials.password != self._passwords[credentials.username]:
                return defer.fail(UnauthorizedLogin("Wrong password!"))
            else:
                return defer.succeed(credentials.username.encode("utf-8"))
        else:
            raise TypeError("Expected credentials as IUnicodeUsernamePassword, not {}!".format(repr(credentials)))
