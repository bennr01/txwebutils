"""
Tests for L{txwebutils.csauth}.
"""
import six
from six.moves.urllib.parse import urlparse, parse_qs
from twisted.internet import defer
from twisted.web.resource import Resource
from twisted.web.vhost import NameVirtualHost
from twisted.cred import portal
from twisted.trial import unittest
from treq.testing import StubTreq
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


class DebugResource(Resource):
    """
    A simple resource printing important information if self.DEBUG = True.
    You can pass a name to the constructor to easier identify it.
    """
    DEBUG = False
    
    def __init__(self, name="DebugResource"):
        Resource.__init__(self)
        self.name = name
    
    def getChild(self, name, request):
        if self.DEBUG:
            print("{}.getChild: ".format(self.name), name, request)
            print("  Children: ", self.listNames())
            print("  Headers: ", request.requestHeaders)
        child = Resource.getChild(self, name, request)
        if self.DEBUG:
            print("{}.getChild -> ".format(self.name), child)
        return child


class CsauthTests(unittest.TestCase):
    """
    Tests for L{txwebutils.csauth}.
    """
    WEB_NAME     = u"web.localhost"
    AUTH_NAME    = u"auth.localhost"
        
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
                "http://{}/login".format(self.WEB_NAME),
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
                "http://{}/bpage".format(self.WEB_NAME),
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
            url=u"http://{}/auth".format(self.AUTH_NAME),
            )
        arr = DebugResource("auth")
        arr.putChild(b"auth", authpage)
        arr.putChild(b"expire", SessionExpiringResource())
        
        # prepare the web site
        lrr = DebugResource("web")
        
        # add the login page
        loginpage = TestLoginResource(
            u"http://{}/auth".format(self.AUTH_NAME),
            self.SITE_A_TOKEN,
            self.SITE_A_SECRET,
            )
        lrr.putChild(b"login", loginpage)
        
        # add a login page with a different permission
        bpage = TestLoginResource(
            u"http://{}/auth".format(self.AUTH_NAME),
            self.SITE_B_TOKEN,
            self.SITE_B_SECRET,
            )
        lrr.putChild(b"bpage", bpage)
        
        # add a resource with an invalid token/secret combination
        invalidepage = TestLoginResource(
            u"http://{}/auth".format(self.AUTH_NAME),
            self.SITE_A_TOKEN,
            self.SITE_B_SECRET,  # <- site B secret
            )
        lrr.putChild(b"invalid", invalidepage)
        
        # create and install treq stubs
        supersite = NameVirtualHost()
        supersite.addHost(self.AUTH_NAME.encode("ascii"), arr)
        supersite.addHost(self.WEB_NAME.encode("ascii"), lrr)
        supersite.default = DebugResource("default")
        
        self.treq = StubTreq(supersite)
        loginpage._set_request_dispatcher(self.treq)
        bpage._set_request_dispatcher(self.treq)
        invalidepage._set_request_dispatcher(self.treq)
    
    @defer.inlineCallbacks
    def test_login_correct(self):
        """
        Test a correct login.
        """
        # first, GET loginpage
        r = yield self.treq.get(
            u"http://{}/login".format(self.WEB_NAME),
            )
        cookies = r.cookies()
        self.assertEqual(r.code, 200)
        pa_url = r.request.absoluteURI.decode("ascii")
        # ensure we were redirected to the auth server
        self.assertNotIn(six.text_type(self.WEB_NAME), pa_url)
        self.assertIn(six.text_type(self.AUTH_NAME), pa_url)
        # ensure paramters were set correctly
        self.assertIn(u"action=login", pa_url)
        self.assertIn(u"ctoken=", pa_url)
        
        # POST correct login userdata
        r = yield self.treq.post(
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
        self.assertNotIn(six.text_type(self.AUTH_NAME), url)
        self.assertIn(six.text_type(self.WEB_NAME), url)
        
        # ensure content was set correctly
        text = yield r.text()
        self.assertEqual(text, self.USER_A_NAME)
        
        # ensure cookies will keep us logged in
        cr = yield self.treq.get(
            u"http://{}/login".format(self.WEB_NAME),
            cookies=cookies,
        )
        url = cr.request.absoluteURI.decode("ascii")
        self.assertNotIn(six.text_type(self.AUTH_NAME), url)
        self.assertIn(six.text_type(self.WEB_NAME), url)
        
        # expire session
        er = yield self.treq.get(
            u"http://{}/expire".format(self.AUTH_NAME),
            cookies=cookies,
            )
        self.assertEqual(er.code, 200)
        
        # ensure we will no longer be logged in automatically
        cr = yield self.treq.get(
            u"http://{}/login".format(self.WEB_NAME),
            cookies=cookies,
            )
        url = cr.request.absoluteURI.decode("ascii")
        self.assertNotIn(six.text_type(self.WEB_NAME), url)
        self.assertIn(six.text_type(self.AUTH_NAME), url)
    
    @defer.inlineCallbacks
    def test_login_different_perm_correct(self):
        """
        Test a correct login with site b, which has different permissions.
        """
        # first, GET loginpage
        r = yield self.treq.get(
            u"http://{}/bpage".format(self.WEB_NAME),
            )
        cookies = r.cookies()
        self.assertEqual(r.code, 200)
        pa_url = r.request.absoluteURI.decode("ascii")
        # ensure we were redirected to the auth server
        self.assertNotIn(six.text_type(self.WEB_NAME), pa_url)
        self.assertIn(six.text_type(self.AUTH_NAME), pa_url)
        # ensure paramters were set correctly
        self.assertIn(u"action=login", pa_url)
        self.assertIn(u"ctoken=", pa_url)
        
        # POST correct login userdata
        # we use user b this time, so we also check whether different
        # users work
        r = yield self.treq.post(
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
        self.assertNotIn(six.text_type(self.AUTH_NAME), url)
        self.assertIn(six.text_type(self.WEB_NAME), url)
        # ensure we are at the bpade
        self.assertIn(u"bpage", url)
        
        # ensure content was set correctly
        text = yield r.text()
        self.assertEqual(text, six.text_type(len(self.USER_B_NAME)))
        
        # ensure cookies will keep us logged in
        cr = yield self.treq.get(
            u"http://{}/bpage".format(self.WEB_NAME),
            cookies=cookies,
            )
        url = cr.request.absoluteURI.decode("ascii")
        self.assertNotIn(six.text_type(self.AUTH_NAME), url)
        self.assertIn(six.text_type(self.WEB_NAME), url)
        self.assertIn(u"bpage", url)
    
    @defer.inlineCallbacks
    def test_crossite_cookies(self):
        """
        Test that cookies will kept you logged in across sites.
        """
        # first, GET loginpage
        r = yield self.treq.get(
            u"http://{}/login".format(self.WEB_NAME),
            )
        cookies = r.cookies()
        self.assertEqual(r.code, 200)
        pa_url = r.request.absoluteURI.decode("ascii")
        # ensure we were redirected to the auth server
        self.assertNotIn(six.text_type(self.WEB_NAME), pa_url)
        self.assertIn(six.text_type(self.AUTH_NAME), pa_url)
        self.assertIn(u"login", pa_url)
        # ensure paramters were set correctly
        self.assertIn(u"action=login", pa_url)
        self.assertIn(u"ctoken=", pa_url)
        
        # POST correct login userdata
        r = yield self.treq.post(
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
        self.assertNotIn(six.text_type(self.AUTH_NAME), url)
        self.assertIn(six.text_type(self.WEB_NAME), url)
        
        # ensure content was set correctly
        text = yield r.text()
        self.assertEqual(text, self.USER_A_NAME)
        
        # GET bpage
        r = yield self.treq.get(
            u"http://{}/bpage".format(self.WEB_NAME),
            cookies=cookies,
            )
        self.assertEqual(r.code, 200)
        url = r.request.absoluteURI.decode("ascii")
        # ensure we were not redirected to the auth server
        self.assertIn(six.text_type(self.WEB_NAME), url)
        self.assertNotIn(six.text_type(self.AUTH_NAME), url)
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
        r = yield self.treq.get(
            u"http://{}/login".format(self.WEB_NAME),
            )
        cookies = r.cookies()
        self.assertEqual(r.code, 200)
        pa_url = r.request.absoluteURI.decode("ascii")
        # ensure we were redirected to the auth server
        self.assertNotIn(six.text_type(self.WEB_NAME), pa_url)
        self.assertIn(six.text_type(self.AUTH_NAME), pa_url)
        # ensure paramters were set correctly
        self.assertIn(u"action=login", pa_url)
        self.assertIn(u"ctoken=", pa_url)
        
        # POST incorrect login userdata
        r = yield self.treq.post(
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
        self.assertIn(six.text_type(self.AUTH_NAME), url)
        self.assertNotIn(six.text_type(self.WEB_NAME), url)
        
        # ensure a malicious request back to the webserver will fail
        qs = urlparse(url).query
        ctoken = parse_qs(qs)[u"ctoken"]
        r = yield self.treq.get(
            u"http://{}/login?action=callback&ctoken={}".format(
                self.WEB_NAME,
                ctoken,
                ),
            cookies=cookies,
            )
        cookies = r.cookies()
        self.assertEqual(r.code, 200)
        pa_url = r.request.absoluteURI.decode("ascii")
        # ensure we were redirected to the auth server
        self.assertNotIn(six.text_type(self.WEB_NAME), pa_url)
        self.assertIn(six.text_type(self.AUTH_NAME), pa_url)
    
    @defer.inlineCallbacks
    def test_token_secret_invalid(self):
        """
        Test an invalid token/secret.
        """
        # first, GET loginpage
        r = yield self.treq.get(
            u"http://{}/invalid".format(self.WEB_NAME),
            )
        cookies = r.cookies()
        self.assertEqual(r.code, 500)
        pa_url = r.request.absoluteURI.decode("ascii")
        # ensure we were not redirected to the auth server
        self.assertIn(six.text_type(self.WEB_NAME), pa_url)
        self.assertNotIn(six.text_type(self.AUTH_NAME), pa_url)
