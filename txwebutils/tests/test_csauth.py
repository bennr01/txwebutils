"""
Tests for L{txwebutils.csauth}.
"""
import six
from six.moves.urllib.parse import urlparse, parse_qs
from twisted.internet import defer, reactor
from twisted.internet.tcp import Client
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.web.resource import Resource
from twisted.web.server import Site
from twisted.cred import portal
from twisted.trial import unittest
import treq
from treq._utils import get_global_pool, set_global_pool
from zope.interface import implementer


from txwebutils.csauth import AuthResource, WebLoginResource, cred, icsauth
from txwebutils.csauth.helper import BasicLoginResource


@implementer(icsauth.IUserData)
class TestUserData(object):
    """
    Test userdata implementation.
    
    @param username: name of user
    @type username: L{six.text_type}
    @attr username: name of user
    @type username: L{six.text_type}
    """
    def __init__(self, username):
        assert isinstance(username, six.text_type)
        self.username = username


@implementer(portal.IRealm)
class TestUserRealm(object):
    """
    Realm implementation for the user data in tests.
    """
    def requestAvatar(self, avatarId, mind, *interfaces):
        if icsauth.IUserData in interfaces:
            return icsauth.IUserData, TestUserData(avatarId.decode("utf-8")), lambda: None
        else:
            raise NotImplementedError()


@implementer(icsauth.IWebAuthPermission)
class TestWebAuthPermission(object):
    """
    Test implementation of the web auth permission.
    
    @param name: name of site
    @type name: L{six.text_type}
    @attr name: name of site
    @type name: L{six.text_type}
    @param full_username: whether the site has access to the full username
    @type full_username: L{bool}
    """
    def __init__(self, name, callback_url, full_username):
        assert isinstance(name, six.text_type)
        assert isinstance(full_username, int)
        self.name = name
        self.callback_url = callback_url
        self._full_username = full_username
    
    def userdata_to_dict(self, userdata):
        if self._full_username:
            username = userdata.username
        else:
            username = six.text_type(len(userdata.username))
        return {u"username": username}


@implementer(portal.IRealm)
class TestSiteRealm(object):
    """
    Realm implementation for the site auth in tests.
    """
    def __init__(self):
        self._token2auth = {}
    
    def register_csauth_perm(self, token, perm):
        """
        Register a CS-Auth permission for a token.
        
        @param token: token for authentication.
        @type token: L{six.text_type}
        @param perm: permission for the token
        @type token: L{TestWebAuthPermission}
        """
        assert isinstance(token, six.text_type)
        assert token not in self._token2auth
        self._token2auth[token] = perm
        
    def requestAvatar(self, avatarId, mind, *interfaces):
        assert isinstance(avatarId, six.binary_type)
        if icsauth.IWebAuthPermission in interfaces:
            return icsauth.IWebAuthPermission, self._token2auth[avatarId.decode("utf-8")], lambda: None
        else:
            raise NotImplementedError()


class SessionExpiringResource(Resource):
    """
    A Resource which expires the sesion on render.
    
    This is used to cleanup the reactor after a test finishes.
    """
    def render_GET(self, request):
        request.getSession().expire()
        return b"session expired"



class TestLoginResource(WebLoginResource):
    """
    Test implementation of a L{txwebutils.csauth.WebLoginResource}.
    """
    def on_login(self, request, userdata):
        return userdata["username"]


class CsauthTests(unittest.TestCase):
    """
    Tests for L{txwebutils.csauth}.
    """
    WEB_SERVER_PORT     = 8080
    AUTH_SERVER_PORT    = 8081
    
    SITE_A_NAME   = u"Site Alpha"
    SITE_A_TOKEN  = u"site a token"
    SITE_A_SECRET = u"secret for a"
    SITE_B_NAME   = u"Site Beta"
    SITE_B_TOKEN  = u"site B token"
    SITE_B_SECRET = u"secret for _b_"
    
    USER_A_NAME   = u"UserA"
    USER_A_PSWD   = u"PswdA"
    USER_B_NAME   = u"IAmUserB"
    USER_B_PSWD   = u"P-S-W-D_B"
    
    @defer.inlineCallbacks
    def setUp(self):
        # prepare the authentication systems
        self.userdb = cred.InMemoryUnicodeUsernamePasswordDatabase()
        self.sitedb = cred.InMemoryUnicodeUsernamePasswordDatabase()
        self.userrealm = TestUserRealm()
        self.siterealm = TestSiteRealm()
        self.userportal = portal.Portal(self.userrealm)
        self.siteportal = portal.Portal(self.siterealm)
        self.userportal.registerChecker(self.userdb)
        self.siteportal.registerChecker(self.sitedb)
        
        # register tokens
        self.sitedb.addUser(
            self.SITE_A_TOKEN,
            self.SITE_A_SECRET,
            )
        self.siterealm.register_csauth_perm(
            self.SITE_A_TOKEN,
            TestWebAuthPermission(
                self.SITE_A_NAME,
                "http://localhost:{}/login".format(self.WEB_SERVER_PORT),
                full_username=True,
                ),
            )
        self.sitedb.addUser(
            self.SITE_B_TOKEN,
            self.SITE_B_SECRET,
            )
        self.siterealm.register_csauth_perm(
            self.SITE_B_TOKEN,
            TestWebAuthPermission(
                self.SITE_B_NAME,
                "http://localhost:{}/bpage".format(self.WEB_SERVER_PORT),
                full_username=False,
                ),
            )
        
        # register Users
        self.userdb.addUser(
            self.USER_A_NAME,
            self.USER_A_PSWD,
            )
        self.userdb.addUser(
            self.USER_B_NAME,
            self.USER_B_PSWD,
            )
        
        # prepare the auth site
        lr = BasicLoginResource()
        authpage = AuthResource(
            self.siteportal,
            self.userportal,
            lr,
            url=u"http://localhost:{}/auth".format(self.AUTH_SERVER_PORT),
            )
        arr = Resource()
        arr.putChild(b"auth", authpage)
        arr.putChild(b"expire", SessionExpiringResource())
        self.auth_site = Site(arr)
        self.auth_site.displayTracebacks = True
        
        # prepare the web site
        lrr = Resource()
        self.web_site = Site(lrr)
        self.web_site.displayTracebacks = True
        
        # add the login page
        loginpage = TestLoginResource(
            u"http://localhost:{}/auth".format(self.AUTH_SERVER_PORT),
            self.SITE_A_TOKEN,
            self.SITE_A_SECRET,
            )
        lrr.putChild(b"login", loginpage)
        
        # add a login page with a different permission
        bpage = TestLoginResource(
            u"http://localhost:{}/auth".format(self.AUTH_SERVER_PORT),
            self.SITE_B_TOKEN,
            self.SITE_B_SECRET,
            )
        lrr.putChild(b"bpage", bpage)
        
        # add a resource with an invalid token/secret combination
        invalidepage = TestLoginResource(
            u"http://localhost:{}/auth".format(self.AUTH_SERVER_PORT),
            self.SITE_A_TOKEN,
            self.SITE_B_SECRET,  # <- site B secret
            )
        lrr.putChild(b"invalid", invalidepage)
        
        # serve
        self.auth_site_ep = TCP4ServerEndpoint(
            reactor,
            self.AUTH_SERVER_PORT,
            interface=b"localhost",
        )
        self.web_site_ep = TCP4ServerEndpoint(
            reactor,
            self.WEB_SERVER_PORT,
            interface=b"localhost",
        )
        self.auth_site_port = yield self.auth_site_ep.listen(self.auth_site)
        self.web_site_port  = yield self.web_site_ep.listen(self.web_site)
    
    @defer.inlineCallbacks
    def tearDown(self):
        # close server endpoints
        yield self.auth_site_port.stopListening()
        yield self.web_site_port.stopListening()
        
        # close pool
        pool = get_global_pool()
        yield pool.closeCachedConnections()
        while True:
            fds = set(reactor.getReaders() + reactor.getReaders())
            if not [fd for fd in fds if isinstance(fd, Client)]:
                break
            else:
                d = defer.Deferred()
                reactor.callLater(0, d.callback, None)
                yield d
        
        # expire all sessions
        for sid in list(self.auth_site.sessions.keys()):
            self.auth_site.sessions[sid].expire()
    
    @defer.inlineCallbacks
    def test_login_correct(self):
        """
        Test a correct login.
        """
        # first, GET loginpage
        r = yield treq.get(
            u"http://localhost:{}/login".format(self.WEB_SERVER_PORT),
            )
        cookies = r.cookies()
        self.assertEqual(r.code, 200)
        pa_url = r.request.absoluteURI.decode("ascii")
        # ensure we were redirected to the auth server
        self.assertNotIn(six.text_type(self.WEB_SERVER_PORT), pa_url)
        self.assertIn(six.text_type(self.AUTH_SERVER_PORT), pa_url)
        # ensure paramters were set correctly
        self.assertIn(u"action=login", pa_url)
        self.assertIn(u"ctoken=", pa_url)
        
        # POST correct login userdata
        r = yield treq.post(
            pa_url,
            params={
                u"username": self.USER_A_NAME,
                u"password": self.USER_A_PSWD,
                },
            cookies=cookies,
            browser_like_redirects=True,
        )
        self.assertEqual(r.code, 200)
        url = r.request.absoluteURI.decode("ascii")
        # ensure we were redirected back to webserver
        self.assertNotIn(six.text_type(self.AUTH_SERVER_PORT), url)
        self.assertIn(six.text_type(self.WEB_SERVER_PORT), url)
        
        # ensure content was set correctly
        text = yield r.text()
        self.assertEqual(text, self.USER_A_NAME)
        
        # ensure cookies will keep us logged in
        cr = yield treq.get(
            u"http://localhost:{}/login".format(self.WEB_SERVER_PORT),
            cookies=cookies,
            )
        url = cr.request.absoluteURI.decode("ascii")
        self.assertNotIn(six.text_type(self.AUTH_SERVER_PORT), url)
        self.assertIn(six.text_type(self.WEB_SERVER_PORT), url)
        
        # expire session
        er = yield treq.get(
            u"http://localhost:{}/expire".format(self.AUTH_SERVER_PORT),
            cookies=cookies,
            )
        self.assertEqual(er.code, 200)
        
        # ensure we will no longer be logged in automatically
        cr = yield treq.get(
            u"http://localhost:{}/login".format(self.WEB_SERVER_PORT),
            cookies=cookies,
            )
        url = cr.request.absoluteURI.decode("ascii")
        self.assertNotIn(six.text_type(self.WEB_SERVER_PORT), url)
        self.assertIn(six.text_type(self.AUTH_SERVER_PORT), url)
    
    @defer.inlineCallbacks
    def test_login_different_perm_correct(self):
        """
        Test a correct login with site b, which has different permissions.
        """
        # first, GET loginpage
        r = yield treq.get(
            u"http://localhost:{}/bpage".format(self.WEB_SERVER_PORT),
            )
        cookies = r.cookies()
        self.assertEqual(r.code, 200)
        pa_url = r.request.absoluteURI.decode("ascii")
        # ensure we were redirected to the auth server
        self.assertNotIn(six.text_type(self.WEB_SERVER_PORT), pa_url)
        self.assertIn(six.text_type(self.AUTH_SERVER_PORT), pa_url)
        # ensure paramters were set correctly
        self.assertIn(u"action=login", pa_url)
        self.assertIn(u"ctoken=", pa_url)
        
        # POST correct login userdata
        # we use user b this time, so we also check whether different
        # users work
        r = yield treq.post(
            pa_url,
            params={
                u"username": self.USER_B_NAME,
                u"password": self.USER_B_PSWD,
                },
            cookies=cookies,
            browser_like_redirects=True,
        )
        self.assertEqual(r.code, 200)
        url = r.request.absoluteURI.decode("ascii")
        # ensure we were redirected back to webserver
        self.assertNotIn(six.text_type(self.AUTH_SERVER_PORT), url)
        self.assertIn(six.text_type(self.WEB_SERVER_PORT), url)
        # ensure we are at the bpade
        self.assertIn(u"bpage", url)
        
        # ensure content was set correctly
        text = yield r.text()
        self.assertEqual(text, six.text_type(len(self.USER_B_NAME)))
        
        # ensure cookies will keep us logged in
        cr = yield treq.get(
            u"http://localhost:{}/bpage".format(self.WEB_SERVER_PORT),
            cookies=cookies,
            )
        url = cr.request.absoluteURI.decode("ascii")
        self.assertNotIn(six.text_type(self.AUTH_SERVER_PORT), url)
        self.assertIn(six.text_type(self.WEB_SERVER_PORT), url)
        self.assertIn(u"bpage", url)
    
    @defer.inlineCallbacks
    def test_crossite_cookies(self):
        """
        Test that cookies will kept you logged in across sites.
        """
        # first, GET loginpage
        r = yield treq.get(
            u"http://localhost:{}/login".format(self.WEB_SERVER_PORT),
            )
        cookies = r.cookies()
        self.assertEqual(r.code, 200)
        pa_url = r.request.absoluteURI.decode("ascii")
        # ensure we were redirected to the auth server
        self.assertNotIn(six.text_type(self.WEB_SERVER_PORT), pa_url)
        self.assertIn(six.text_type(self.AUTH_SERVER_PORT), pa_url)
        self.assertIn(u"login", pa_url)
        # ensure paramters were set correctly
        self.assertIn(u"action=login", pa_url)
        self.assertIn(u"ctoken=", pa_url)
        
        # POST correct login userdata
        r = yield treq.post(
            pa_url,
            params={
                u"username": self.USER_A_NAME,
                u"password": self.USER_A_PSWD,
                },
            cookies=cookies,
            browser_like_redirects=True,
        )
        self.assertEqual(r.code, 200)
        url = r.request.absoluteURI.decode("ascii")
        # ensure we were redirected back to webserver
        self.assertNotIn(six.text_type(self.AUTH_SERVER_PORT), url)
        self.assertIn(six.text_type(self.WEB_SERVER_PORT), url)
        
        # ensure content was set correctly
        text = yield r.text()
        self.assertEqual(text, self.USER_A_NAME)
        
        # GET bpage
        r = yield treq.get(
            u"http://localhost:{}/bpage".format(self.WEB_SERVER_PORT),
            cookies=cookies,
            )
        self.assertEqual(r.code, 200)
        url = r.request.absoluteURI.decode("ascii")
        # ensure we were not redirected to the auth server
        self.assertIn(six.text_type(self.WEB_SERVER_PORT), url)
        self.assertNotIn(six.text_type(self.AUTH_SERVER_PORT), url)
        self.assertIn(u"bpage", url)
        # ensure content is still correct
        # this is important, since the different sites have different
        # access to the userdata
        text = yield r.text()
        self.assertEqual(text, six.text_type(len(self.USER_A_NAME)))
    
    @defer.inlineCallbacks
    def test_login_invalid(self):
        """
        Test an invalid login.
        """
        # first, GET loginpage
        r = yield treq.get(
            u"http://localhost:{}/login".format(self.WEB_SERVER_PORT),
            )
        cookies = r.cookies()
        self.assertEqual(r.code, 200)
        pa_url = r.request.absoluteURI.decode("ascii")
        # ensure we were redirected to the auth server
        self.assertNotIn(six.text_type(self.WEB_SERVER_PORT), pa_url)
        self.assertIn(six.text_type(self.AUTH_SERVER_PORT), pa_url)
        # ensure paramters were set correctly
        self.assertIn(u"action=login", pa_url)
        self.assertIn(u"ctoken=", pa_url)
        
        # POST incorrect login userdata
        r = yield treq.post(
            pa_url,
            params={
                u"username": self.USER_A_NAME,
                u"password": self.USER_B_PSWD,  # <- user b password
                },
            cookies=cookies,
            browser_like_redirects=True,
        )
        self.assertEqual(r.code, 401)
        url = r.request.absoluteURI.decode("ascii")
        # ensure we were not redirected back to webserver
        self.assertIn(six.text_type(self.AUTH_SERVER_PORT), url)
        self.assertNotIn(six.text_type(self.WEB_SERVER_PORT), url)
        
        # ensure a malicious request back to the webserver will fail
        qs = urlparse(url).query
        ctoken = parse_qs(qs)[u"ctoken"]
        r = yield treq.get(
            u"http://localhost:{}/login?action=callback&ctoken={}".format(
                self.WEB_SERVER_PORT,
                ctoken,
                ),
            cookies=cookies,
            )
        cookies = r.cookies()
        self.assertEqual(r.code, 200)
        pa_url = r.request.absoluteURI.decode("ascii")
        # ensure we were redirected to the auth server
        self.assertNotIn(six.text_type(self.WEB_SERVER_PORT), pa_url)
        self.assertIn(six.text_type(self.AUTH_SERVER_PORT), pa_url)
    
    @defer.inlineCallbacks
    def test_token_secret_invalid(self):
        """
        Test an invalid token/secret.
        """
        # first, GET loginpage
        r = yield treq.get(
            u"http://localhost:{}/invalid".format(self.WEB_SERVER_PORT),
            )
        cookies = r.cookies()
        self.assertEqual(r.code, 500)
        pa_url = r.request.absoluteURI.decode("ascii")
        # ensure we were not redirected to the auth server
        self.assertIn(six.text_type(self.WEB_SERVER_PORT), pa_url)
        self.assertNotIn(six.text_type(self.AUTH_SERVER_PORT), pa_url)
